from .circleci import Executor, JobInstance, Pipeline, StepsJob, Workflow
from .steps import (
    bootstrap_steps,
    cache_eval_jobs,
    continuation,
    generate_main_pipeline,
    nix_eval_jobs,
)


def run() -> None:
    p = Pipeline(setup=True)
    docker = p.executor(
        "docker_large",
        Executor.docker(image="nixos/nix:latest", resource_class="large"),
    )
    setup = p.job(
        "setup",
        StepsJob(
            executor=docker,
            shell="/tmp/python/bin/python",
            steps=bootstrap_steps()
            + [
                nix_eval_jobs.bind("(import ./test/release.nix{})"),
                cache_eval_jobs,
                generate_main_pipeline,
                continuation,
            ],
        ),
    )
    p.workflow("setup", Workflow(jobs=[JobInstance(job=setup)]))
    print(p.dump_yaml())
