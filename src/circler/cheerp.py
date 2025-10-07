from .circleci import Executor, Job, JobInstance, Pipeline, Workflow
from .steps import bootstrap_steps, continuation, generate_main_pipeline, nix_eval_jobs


def run() -> None:
    p = Pipeline(setup=True)
    docker = p.executor(
        "docker_large",
        Executor.docker(image="nixos/nix:latest", resource_class="large"),
    )
    setup = p.job(
        "setup",
        Job(
            executor=docker,
            shell="/tmp/python/bin/python",
            steps=bootstrap_steps()
            + [
                nix_eval_jobs.bind("(import ./test/release.nix{})"),
                generate_main_pipeline,
                continuation,
            ],
        ),
    )
    p.workflow("setup", Workflow(jobs=[JobInstance(job=setup)]))
    print(p.dump_yaml())
