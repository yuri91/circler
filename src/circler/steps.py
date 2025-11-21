import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Self

from .circleci import (
    DictRef,
    Executor,
    JobInstance,
    NoOpJob,
    Pipeline,
    Run,
    Step,
    StepsJob,
    Workflow,
)
from .drv import Derivation, get_safe_name, load_derivations
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
        self.shell = shell or "/tmp/python/bin/python"
        super().__init__(name, cmd, self.shell)

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


checkout = Run(
    name="Clone and checkout repo",
    shell="/bin/sh",
    command="""
mkdir -p ~/.ssh
echo 'github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
' >> ~/.ssh/known_hosts
git clone $CIRCLE_REPOSITORY_URL --revision=$CIRCLE_SHA1 --depth 1 .
""",
)


@dataclass
class GitRev:
    repo: str
    branch: str
    sha: str | None


@step(name="Update pin of trigger repo and commit")
def update_pin_and_commit() -> None:
    repo = env["CIRCLER_TRIGGER_REPO_NAME"]
    branch = env["CIRCLER_TRIGGER_BRANCH"]
    sha = env["CIRCLER_TRIGGER_CHECKOUT_SHA"]
    ci_num = env["CIRCLE_BUILD_NUM"]
    ci_repo = env["CIRCLE_PROJECT_REPONAME"]
    ci_branch = f"{ci_repo}-{ci_num}"
    parameters: dict[str, str] = {}
    for k,v in env.items():
        if not k.startswith("CIRCLER_PARAM_"):
            continue
        parameters[k.removeprefix("CIRCLER_PARAM_")] = v
    revs = []
    do_merge = True
    if repo != ci_repo:
        do_merge = branch == "main" or branch == "master"
        revs.append(GitRev(repo, branch, sha))
    for p, b in parameters.items():
        if p.endswith("_branch") and b != "":
            do_merge = False
            revs.append(GitRev(p.removesuffix("_branch"), b, sha=None))
    sh.git.switch(c=ci_branch)
    with open("npins/sources.json") as f:
        npins = json.load(f)
    for r in revs:
        owner = npins[r.repo]["repository"]["owner"]
        if r.sha:
            sh.npins.add.github(owner, repo, b=r.branch, at=r.sha)
        else:
            sh.npins.add.github(owner, repo, b=r.branch)
    if len(revs) > 0:
        sh.git.add("npins/sources.json")
        sh.git.commit(m=f"[CI] {repo}:{branch} {sha}")
    if do_merge:
        export("BRANCH_TO_MERGE", ci_branch)
    sh.git.push("--set-upstream", "origin", ci_branch)


@step(name="Merge CI branch to master")
def merge_ci_branch(ci_branch: str) -> None:
    sh.git.fetch(ci_branch)
    sh.git.merge(ci_branch)
    sh.git.push.origin("master")


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
env | grep CIRCLER
nix build github:yuri91/circler#python --out-link /tmp/python
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
    export("SHELL_PATH", os.readlink("/tmp/python") + "/bin/python")


@step(name="Cache eval jobs")
def cache_eval_jobs() -> None:
    items = env["EVAL_JOBS"]
    for i in items:
        sh.attic.push("lt:cheerp", i["drvPath"])


@step(name="Cache built derivation outputs")
def cache_drv_outputs(outs: list[str]) -> None:
    for o in outs:
        sh.attic.push("lt:cheerp", o)


def bootstrap_steps() -> list[Step]:
    return [
        checkout,
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
    p = generate_build_pipeline(drvs)
    print(p.dump_yaml())
    export("NEXT_PIPELINE", p.dump_json())


@step(name="Trigger continuation")
def continuation() -> None:
    import requests

    pipeline = env["NEXT_PIPELINE"]
    payload = {
        "continuation-key": os.environ["CIRCLE_CONTINUATION_KEY"],
        "configuration": pipeline,
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
    out = sh.nix_store(_long_sep=None, realize=path)
    export("OUT_PATHS", out.splitlines())


def generate_build_job(
    p: Pipeline, executor: DictRef[Executor], drv: Derivation
) -> JobInstance:
    shell_path = env["SHELL_PATH"]
    job = p.job(
        get_safe_name(drv.name),
        StepsJob(
            executor=executor,
            shell=shell_path,
            steps=setup_steps(shell_path)
            + [
                realize_drv.bind(drv.drv),
                cache_drv_outputs.bind(list(drv.outputs.values())),
            ],
        ),
    )
    return JobInstance(job)


def prune_deps(jobs: dict[str, JobInstance]) -> dict[str, JobInstance]:
    import numpy as np
    import numpy.typing as npt

    def transitive_reduction(
        adj_matrix: npt.NDArray[np.bool_],
    ) -> npt.NDArray[np.bool_]:
        n = len(adj_matrix)
        reach_indirect = np.zeros((n, n), dtype=bool)
        temp = adj_matrix.copy()
        for _ in range(n - 1):
            temp = temp @ adj_matrix
            reach_indirect |= temp
        reduction: npt.NDArray[np.bool_] = adj_matrix & ~reach_indirect
        return reduction

    nodes = list(jobs.keys())
    nodes_idx_map = {n: i for i, n in enumerate(nodes)}
    size = len(nodes)
    adj = np.zeros((size, size), dtype=bool)
    for i in range(size):
        for v in jobs[nodes[i]].requires:
            j = nodes_idx_map[v.key]
            adj[i][j] = True
    adj = transitive_reduction(adj)
    ret = {}
    for i in range(size):
        job: JobInstance = jobs[nodes[i]]
        requires = []
        for j in range(size):
            if not adj[i][j]:
                continue
            requires.append(jobs[nodes[j]].job)
        ret_v = JobInstance(job.job, job.arguments, requires)
        ret[nodes[i]] = ret_v
    return ret


def generate_build_pipeline(drvs: dict[str, Derivation]) -> Pipeline:
    p = Pipeline(setup=False)
    docker = p.executor(
        "docker_large",
        Executor.docker(image="nixos/nix:latest", resource_class="large"),
    )
    jobs: dict[str, JobInstance] = {}
    for drv in drvs.values():
        jobs[get_safe_name(drv.name)] = generate_build_job(p, docker, drv)

    for name in jobs:
        for dep in drvs[name].deps:
            jobs[name].requires.append(jobs[dep.name].job)

    jobs["built-all"] = JobInstance(
        job=p.job("built-all", NoOpJob()), requires=[j.job for j in jobs.values()]
    )
    jobs = prune_deps(jobs)
    if "BRANCH_TO_MERGE" in env:
        ci_branch = env["BRANCH_TO_MERGE"]
        jobs["merge-to-master"] = JobInstance(
            job=p.job(
                "merge-to-master",
                StepsJob(
                    executor=docker,
                    shell=env["SHELL_PATH"],
                    steps=[checkout, merge_ci_branch.bind(ci_branch)],
                ),
            ),
            requires=[jobs["built-all"].job],
        )
    p.workflow("build-all", Workflow(jobs=list(jobs.values())))
    return p
