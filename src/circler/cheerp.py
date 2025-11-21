from .circleci import (
    Executor,
    JobInstance,
    Parameter,
    Pipeline,
    StepsJob,
    Workflow,
    circler_environment,
)
from .steps import (
    bootstrap_steps,
    cache_eval_jobs,
    continuation,
    generate_main_pipeline,
    nix_eval_jobs,
    update_pin_and_commit,
)


def run() -> None:
    params = {"cheerp_compiler_branch": Parameter("string", "")}
    p = Pipeline(setup=True, parameters=params)
    docker = p.executor(
        "docker_large",
        Executor.docker(image="nixos/nix:latest", resource_class="large"),
    )
    setup = p.job(
        "setup",
        StepsJob(
            executor=docker,
            environment=circler_environment(params),
            steps=bootstrap_steps()
            + [
                update_pin_and_commit,
                nix_eval_jobs.bind("(import ./default.nix{}).ci.release"),
                cache_eval_jobs,
                generate_main_pipeline,
                continuation,
            ],
        ),
    )
    p.workflow("setup", Workflow(jobs=[JobInstance(job=setup)]))
    print(p.dump_yaml())
