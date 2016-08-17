import datetime
import json

from alchemyjsonschema.dictify import datetime_rfc3339
from autobahn.twisted.wamp import ApplicationSession, ApplicationRunner
from tapp_config import setup_redis, setup_logging
from twisted.internet.defer import inlineCallbacks

from poloniex_manager import Poloniex

red = setup_redis()

channels = {}
poloniex = Poloniex()
logger = setup_logging('poloniex_listener', prefix="trademanager", cfg=poloniex.cfg)
poloniex.setup_connections()
poloniex.setup_logger()  # will be actually use the logger above


def on_ticker(*ticker):
    market = poloniex.format_market(ticker[0])
    jtick = {'bid': float(ticker[3]), 'ask': float(ticker[2]), 'last': float(ticker[1]), 'high': float(ticker[8]),
             'low': float(ticker[9]), 'volume': float(ticker[6]),
             'market': market, 'exchange': 'poloniex',
             'time': datetime_rfc3339(datetime.datetime.utcnow())}
    red.set('poloniex_%s_ticker' % market, json.dumps(jtick))
    logger.debug("set poloniex %s ticker %s" % (market, jtick))


class PoloniexComponent(ApplicationSession):
    @inlineCallbacks
    def onJoin(self, details):
        yield self.subscribe(on_ticker, 'ticker')


def main():
    runner = ApplicationRunner(u"wss://api.poloniex.com:443", u"realm1")
    runner.run(PoloniexComponent)


if __name__ == "__main__":
    main()
