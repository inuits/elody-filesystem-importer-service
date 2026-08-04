from importlib import import_module
from json import loads
from logging import getLogger
from os import getenv
from typing import Any

from elody.loader import load_queues
from elody.util import (
    CustomJSONEncoder,
    custom_json_dumps,
    get_boolean_env,
)

_rabbit = None


def init_rabbit(app):
    global _rabbit
    amqp_module = import_module(getenv("AMQP_MANAGER", "amqpstorm_flask"))
    auto_delete_exchange = get_boolean_env("AUTO_DELETE_EXCHANGE", False)
    durable_exchange = get_boolean_env("DURABLE_EXCHANGE", True)
    passive_exchange = get_boolean_env("PASSIVE_EXCHANGE", False)
    ExchangeParams = (
        amqp_module.ExchangeParams
        if amqp_module.__name__ == "amqpstorm_flask"
        else amqp_module.ExchangeParams.ExchangeParams
    )
    _rabbit = amqp_module.RabbitMQ(
        exchange_params=ExchangeParams(
            auto_delete=auto_delete_exchange,
            durable=durable_exchange,
            passive=passive_exchange,
        )
    )
    if amqp_module.__name__ == "amqpstorm_flask":
        _rabbit.init_app(
            app, "basic", loads, custom_json_dumps, json_encoder=CustomJSONEncoder
        )
    else:
        _rabbit.init_app(app, "basic", loads, custom_json_dumps)
    load_queues(getLogger(__name__))


def get_rabbit() -> Any:
    global _rabbit  # noqa: PLW0602
    return _rabbit
