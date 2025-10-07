import json
import os
from collections.abc import Callable
from typing import Any, Self

from .circleci import (
    Checkout,
    DictRef,
    Executor,
    Job,
    JobInstance,
    Pipeline,
    Run,
    Step,
    Workflow,
)
from .drv import Derivation, get_safe_name, load_derivations, prune_graph
from .exec import env, export, sh


class CallableRunStep(Run):
    def __init__(
        self,
        name: str,
        shell: str | None,
        fn: Callable[..., None],
        args: list[Any] | None = None,
    ):
        args = args or []
        arg_str = ",".join(repr(a) for a in args)
        cmd = f"""
from {fn.__module__} import {fn.__name__}
{fn.__name__}({arg_str})
"""
        self.fn = fn
        self.args = args or []
        super().__init__(name, cmd, shell)

    def bind(self, *args: Any) -> Self:
        ret = type(self)(self.name, self.shell, self.fn, list(args))
        return ret

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.fn(*args, **kwargs)


def step(
    name: str, shell: str | None = None
) -> Callable[[Callable[..., None]], CallableRunStep]:
    def inner(func: Callable[..., None]) -> CallableRunStep:
        return CallableRunStep(name, shell, func)

    return inner


def nix_conf(cores: int, max_jobs: int) -> str:
    return f"""
experimental-features = nix-command flakes ca-derivations
cores = {cores}
max-jobs = {max_jobs}
sandbox = false
sandbox-fallback = true
system-features = nixos-test benchmark big-parallel kvm
substituters = https://cache.nixos.org/
trusted-public-keys = cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=
trusted-users = root circleci
"""


def attic_setup(url: str, name: str, cache: str) -> Step:
    return Run(
        name="Setup Attic",
        shell="/bin/sh",
        command=f"""
nix run nixpkgs#attic-client -- login {name} {url} ${{ATTIC_TOKEN}}
nix run nixpkgs#attic-client -- use {name}:{cache}
""",
    )


@step(name="Eval nix expression")
def nix_eval_jobs(expr: str) -> None:
    out = sh.nix_eval_jobs(
        _long_sep=None,
        expr=expr,
        workers=2,
        max_memory_size="2G",
        verbose=True,
        log_format="raw",
        check_cache_status=True,
    )
    items = []
    for line in out.strip().split("\n"):
        i = json.loads(line)
        items.append(i)
    export("EVAL_JOBS", items)


nix_setup = Run(
    name="Setup nix",
    shell="/bin/sh",
    command=f"""
cat \\<< 'EOF' >/etc/nix/nix.conf
{nix_conf(cores=4, max_jobs=2).strip()}
EOF
""",
)
shell_bootstrap = Run(
    name="Bootstrap shell",
    shell="/bin/sh",
    command="""
nix build .#python --out-link /tmp/python
""",
)


def shell_setup(shell_path: str) -> Step:
    return Run(
        name="Setup shell",
        shell="/bin/sh",
        command=f"""
nix-store --add-root /tmp/python --realize {shell_path}
    """,
    )


@step(name="Cache python shell")
def cache_shell() -> None:
    sh.attic.push("lt:cheerp", "/tmp/python")
    export("SHELL_PATH", os.readlink("/tmp/python"))


def bootstrap_steps() -> list[Step]:
    return [
        Checkout(),
        nix_setup,
        attic_setup("https://nix.leaningtech.com", "lt", "cheerp"),
        shell_bootstrap,
        cache_shell,
    ]


def setup_steps(shell_path: str) -> list[Step]:
    return [
        nix_setup,
        attic_setup("https://nix.leaningtech.com", "lt", "cheerp"),
        shell_setup(shell_path),
    ]


@step(name="Generate main pipeline")
def generate_main_pipeline() -> None:
    items = env["EVAL_JOBS"]
    drvs = load_derivations(items)
    drvs = prune_graph(drvs)
    p = generate_build_pipeline(drvs)
    export("NEXT_PIPELINE", p)


@step(name="Trigger continuation")
def continuation() -> None:
    import requests

    pipeline = env["NEXT_PIPELINE"]
    assert isinstance(pipeline, Pipeline)
    payload = {
        "continuation-key": os.environ["CIRCLE_CONTINUATION_KEY"],
        "configuration": pipeline.dump_json_str(),
    }
    response = requests.post(
        "https://circleci.com/api/v2/pipeline/continue",
        json=payload,
        headers={"Accept": "application/json"},
    )
    print(response.text)
    pass


@step(name="Realize derivation")
def realize_drv(path: str) -> None:
    out = sh.bake("nix-store")(_long_sep=None, realize=path)
    export("OUT_PATHS", out.splitlines())


def generate_build_job(
    p: Pipeline, executor: DictRef[Executor], drv: Derivation
) -> JobInstance:
    shell_path = env["SHELL_PATH"]
    job = p.job(
        get_safe_name(drv.name),
        Job(
            executor=executor,
            shell=shell_path,
            steps=setup_steps(shell_path) + [realize_drv.bind(drv.drv)],
        ),
    )
    return JobInstance(job)


def generate_build_pipeline(drvs: dict[str, Derivation]) -> Pipeline:
    p = Pipeline(setup=False)
    docker = p.executor(
        "docker_large",
        Executor.docker(image="nixos/nix:latest", resource_class="large"),
    )
    jobs: dict[str, JobInstance] = {}
    for drv in drvs.values():
        jobs[drv.name] = generate_build_job(p, docker, drv)

    for name in jobs:
        for dep in drvs[name].deps:
            jobs[name].requires.append(jobs[dep.name].job)
    p.workflow("build-all", Workflow(jobs=list(jobs.values())))
    return p
