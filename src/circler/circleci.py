from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, is_dataclass
from functools import singledispatch
from typing import Any, Literal

import requests
import yaml


def string_presenter(dumper: yaml.Dumper, data: str) -> Any:
    if "\n" in data:
        data = data.lstrip()
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, string_presenter)


def serialize_base(x: Any, skip: list[str] | None = None) -> Any:
    if isinstance(x, list):
        return [serialize(i) for i in x]
    if isinstance(x, dict):
        return {k: serialize(v) for (k, v) in x.items()}
    if not is_dataclass(x) or isinstance(x, type):
        return x
    ret = {}
    for f in fields(x):
        if skip is not None and f.name in skip:
            continue
        v = getattr(x, f.name)
        if v is None:
            continue
        ret[f.name] = serialize(v)
    return ret


@singledispatch
def serialize(x: Any, skip: list[str] | None = None) -> Any:
    return serialize_base(x, skip)


class DictRef[T]:
    key: str
    _dict: dict[str, T]

    def __init__(self, d: dict[str, T], key: str, init: T | None):
        self.key = key
        self._dict = d
        if init is not None:
            self._dict[self.key] = init

    def deref(self) -> T:
        return self._dict[self.key]


@serialize.register(DictRef)
def _(x: DictRef[Any]) -> str:
    return x.key


@dataclass
class Docker:
    image: str


@serialize.register
def _(x: Docker) -> dict[str, Any]:
    return {"docker": [serialize_base(x)]}


@dataclass
class Executor:
    kind: Docker
    resource_class: str

    @staticmethod
    def docker(image: str, resource_class: str) -> Executor:
        return Executor(Docker(image), resource_class)


@serialize.register
def _(x: Executor) -> dict[str, Any]:
    kind = serialize(x.kind)
    ret = serialize_base(x, skip=["kind"])
    assert isinstance(ret, dict)
    ret.update(kind)
    return ret


@dataclass
class Run:
    name: str
    command: str
    shell: str | None = None
    no_output_timeout: str | None = None


@serialize.register
def _(x: Run) -> dict[str, Any]:
    return {"run": serialize_base(x)}


@dataclass
class Checkout:
    pass


@serialize.register
def _(_: Checkout) -> str:
    return "checkout"


type Step = Run | Checkout


@dataclass
class StepsJob:
    executor: DictRef[Executor]
    steps: list[Step]
    parameters: dict[str, Parameter] | None = None
    environment: dict[str, str] | None = None
    shell: str | None = None


class NoOpJob:
    pass


@serialize.register
def _(_: NoOpJob) -> dict[str, Any]:
    return {"type": "no-op"}


type Job = StepsJob | NoOpJob


@dataclass
class JobInstance:
    job: DictRef[Job]
    arguments: dict[str, Any] = field(default_factory=dict)
    requires: list[DictRef[Job]] = field(default_factory=list)


@serialize.register
def _(x: JobInstance) -> dict[str, Any]:
    data = serialize(x.arguments)
    requires = serialize(x.requires)
    data["requires"] = requires
    return {x.job.key: data}


@dataclass
class Equal:
    lhs: str
    rhs: str


@serialize.register
def _(x: Equal) -> dict[str, Any]:
    return {"equal": [x.lhs, x.rhs]}


@dataclass
class Not:
    cond: Cond


@serialize.register
def _(x: Not) -> dict[str, Any]:
    return {"not": serialize(x.cond)}


type Cond = Equal | Not


@dataclass
class Workflow:
    jobs: list[JobInstance]
    when: Cond | None = None


@dataclass
class Parameter:
    type: str
    default: str | None


@dataclass
class Pipeline:
    version: Literal["2.1"] = "2.1"
    jobs: dict[str, Job] = field(default_factory=dict)
    workflows: dict[str, Workflow] = field(default_factory=dict)
    executors: dict[str, Executor] = field(default_factory=dict)
    parameters: dict[str, Parameter] = field(default_factory=dict)
    setup: bool = False

    def job(self, name: str, j: Job) -> DictRef[Job]:
        return DictRef(self.jobs, name, j)

    def workflow(self, name: str, w: Workflow) -> DictRef[Workflow]:
        return DictRef(self.workflows, name, w)

    def executor(self, name: str, e: Executor) -> DictRef[Executor]:
        return DictRef(self.executors, name, e)

    def parameter(self, name: str, p: Parameter) -> DictRef[Parameter]:
        return DictRef(self.parameters, name, p)

    def dump_yaml(self) -> str:
        d = serialize(self)
        return yaml.dump(d)

    def dump_json(self) -> str:
        d = serialize(self)
        return json.dumps(d)

    def dump_json_str(self) -> str:
        j = self.dump_json()
        return json.dumps(j)

    def exec(self, args: dict[str, Any] | None) -> None:
        if not args:
            args = {}
        payload = {
            "continuation-key": os.environ["CIRCLECI_CONTINUATION_KEY"],
            "configuration": self.dump_json_str(),
            "parameters": args,
        }
        requests.post(
            "https://circleci.com/api/v2/pipeline/continue",
            json=payload,
            headers={"Accept": "application/json"},
        )


def circler_environment(parameters: dict[str, Parameter]) -> dict[str, str]:
    env = {
        "CIRCLER_TRIGGER_REPO_URL": "<< pipeline.trigger_parameters.github_app.repo_url >>",
        "CIRCLER_TRIGGER_REPO_NAME": "<< pipeline.trigger_parameters.github_app.repo_name >>",
        "CIRCLER_TRIGGER_CHECKOUT_SHA": "<< pipeline.trigger_parameters.github_app.checkout_sha >>",
        "CIRCLER_TRIGGER_BRANCH": "<< pipeline.trigger_parameters.github_app.branch >>",
        "CIRCLER_GIT_BRANCH": "<< pipeline.git.branch >>",
        "CIRCLER_GIT_REV": "<< pipeline.git.revision >>",
        "CIRCLER_GIT_BRANCH_IS_DEFAULT": "<< pipeline.git.branch.is_default >>",
    }
    for p in parameters:
        env[f"CIRCLER_PARAM_{p}"] = f"<< pipeline.parameters.{p} >>"
    return env
