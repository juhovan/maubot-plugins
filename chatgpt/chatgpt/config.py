from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("api-key")
        helper.copy("bot-name")
        helper.copy("model")
        helper.copy("max_price_per_token")
        helper.copy("vat")
        helper.copy("site_url")
        helper.copy("site_name")
        helper.copy("tool_support.patterns") 
