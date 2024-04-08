import logging
import os
import secrets

from elody.loader import load_apps, load_policies, load_queues
from flask import Flask
from flask_restful import Api
from flask_swagger_ui import get_swaggerui_blueprint
from healthcheck import HealthCheck
from importlib import import_module
from inuits_policy_based_auth import PolicyFactory

if os.getenv("SENTRY_ENABLED", False) in ["True", "true", True]:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FlaskIntegration()],
        environment=os.getenv("NOMAD_NAMESPACE"),
    )


SWAGGER_URL = "/api/docs"  # URL for exposing Swagger UI (without trailing '/')
API_URL = (
    "/spec/inuits-dams-filesystem-importer-service.json"  # Our API url (can of course be a local resource)
)

swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL)

app = Flask(__name__)
api = Api(app)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))

logging.basicConfig(
    format="%(asctime)s %(process)d,%(threadName)s %(filename)s:%(lineno)d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# amqp_module = importlib.import_module(os.getenv("AMQP_MANAGER", "amqpstorm_flask"))
# auto_delete_exchange = os.getenv("AUTO_DELETE_EXCHANGE", False) in [
#     1,
#     "1",
#     True,
#     "True",
#     "true",
# ]
# durable_exchange = os.getenv("DURABLE_EXCHANGE", True) in [1, "1", True, "True", "true"]
# passive_exchange = os.getenv("PASSIVE_EXCHANGE", False) in [
#     1,
#     "1",
#     True,
#     "True",
#     "true",
# ]
# rabbit = amqp_module.RabbitMQ(
#     exchange_params=amqp_module.ExchangeParams(
#         auto_delete=auto_delete_exchange,
#         durable=durable_exchange,
#         passive=passive_exchange,
#     )
# )
# rabbit.init_app(
#     app, "basic", json.loads, custom_json_dumps, json_encoder=CustomJSONEncoder
# )

app.register_blueprint(swaggerui_blueprint)


# def rabbit_available():
#     connection = rabbit.get_connection()
#     if connection.is_open:
#         return True, "Successfully reached RabbitMQ"
#     return False, "Failed to reach RabbitMQ"

health = HealthCheck()
app.add_url_rule("/health", "healthcheck", view_func=lambda: health.run())

policy_factory = PolicyFactory()
load_apps(app, logger)
try:
    module = import_module("apps.permissions")
    load_policies(policy_factory, logger, module.PERMISSIONS)
except ModuleNotFoundError:
    load_policies(policy_factory, logger)
    
    
# Initialize RabbitMQ Queues
load_queues(logger)

from resources.importer import Importer
from resources.importer import ImporterDirectories, ImporterStart, ListDirectories
from resources.spec import OpenAPISpec

api.add_resource(Importer, "/importer")
api.add_resource(ImporterDirectories, "/importer/directories")
# api.add_resource(ListDirectories, "/import/directories")
api.add_resource(ImporterStart, "/importer/start")
api.add_resource(OpenAPISpec, "/spec/inuits-dams-filesystem-importer-service.json")

if __name__ == "__main__":
    app.run()
