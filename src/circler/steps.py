import os
from collections.abc import Callable

from .circleci import (
    Checkout,
    Executor,
    Job,
    JobInstance,
    Pipeline,
    Run,
    Step,
    Workflow,
)
from .exec import env, export, sh


class CallableRunStep(Run):
    def __init__(self, name: str, shell: str | None, fn: Callable[[], None]):
        cmd = f"""
from {fn.__module__} import {fn.__name__}
{fn.__name__}()
"""
        self.fn = fn
        super().__init__(name, cmd, shell)

    def __call__(self) -> None:
        self.fn()


def step(
    name: str, shell: str | None = None
) -> Callable[[Callable[[], None]], CallableRunStep]:
    def inner(func: Callable[[], None]) -> CallableRunStep:
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
attic login {name} {url} ${{ATTIC_TOKEN}}
attic use {name}:{cache}
""",
    )


def nix_eval_jobs(expr: str) -> Step:
    @step(name="Eval nix expression")
    def run() -> None:
        out = sh.nix_eval_jobs(
            _long_sep=None,
            expr=expr,
            workers=2,
            max_memory_size="2G",
            verbose=True,
            log_format="raw",
            check_cache_status=True,
        )
        export("EVAL_JOBS", out)
    return run


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
    pass


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
