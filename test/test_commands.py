import json
import os
import time
import unittest
from ledger import Amount
from ledger import Balance

from jsonschema import validate
from poloniex_manager import Poloniex

from sqlalchemy_models import get_schemas, wallet as wm, exchange as em

from trade_manager.helper import start_test_man, stop_test_man
from trade_manager.plugin import get_orders, get_trades, sync_ticker, get_debits, sync_balances, \
    get_credits, \
    make_ledger, get_ticker, get_balances, create_order, sync_orders, cancel_orders, sync_credits, sync_debits, \
    sync_trades, get_order_by_order_id

poloniex = Poloniex()  # session=ses)
poloniex.setup_connections()
SCHEMAS = get_schemas()


def test_commodities():
    map = {'BTC': 'BTC',
           'ETH': 'ETH',
           'LTC': 'LTC',
           'USD': 'USDT'}
    for good in map:
        assert poloniex.unformat_commodity(good) == map[good]
        assert poloniex.format_commodity(map[good]) == good


def test_markets():
    map = {'BTC_USD': 'USDT_BTC',
           'ETH_BTC': 'BTC_ETH',
           'LTC_BTC': 'BTC_LTC'}
    for good in map:
        assert poloniex.unformat_market(good) == map[good]
        assert poloniex.format_market(map[good]) == good


class TestPluginRunning(unittest.TestCase):
    def setUp(self):
        start_test_man('poloniex')

    def tearDown(self):
        stop_test_man('poloniex')

    def test_balance(self):
        sync_balances('poloniex')
        countdown = 1000
        total, available = get_balances('poloniex', session=poloniex.session)
        while countdown > 0 and str(total) == '0':
            countdown -= 1
            total, available = get_balances('poloniex', session=poloniex.session)
        assert isinstance(total, Balance)
        assert isinstance(available, Balance)
        assert str(total) != 0
        assert str(available) != 0
        for amount in total:
            assert amount >= available.commodity_amount(amount.commodity)

    def test_order_lifecycle(self):
        order = create_order('poloniex', 100, 0.01, 'BTC_USD', 'bid', session=poloniex.session, expire=time.time()+60)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        oorder = get_orders(oid=order.id, session=poloniex.session)
        countdown = 1000
        while oorder[0].state == 'pending' and countdown > 0:
            countdown -= 1
            oorder = get_orders(oid=order.id, session=poloniex.session)
            if oorder[0].state == 'pending':
                time.sleep(0.01)
                poloniex.session.close()
        assert len(oorder) == 1
        assert oorder[0].state == 'open'
        poloniex.session.close()
        cancel_orders('poloniex', oid=order.id)
        countdown = 1000
        corder = get_orders('poloniex', order_id=oorder[0].order_id, session=poloniex.session)
        while corder[0].state != 'closed' and countdown > 0:
            countdown -= 1
            corder = get_orders('poloniex', order_id=oorder[0].order_id, session=poloniex.session)
            if corder[0].state != 'closed':
                time.sleep(0.01)
                poloniex.session.close()
        assert len(corder) == 1
        assert corder[0].state == 'closed'

    def test_cancel_order_order_id(self):
        poloniex.sync_orders()
        order = create_order('poloniex', 100, 0.01, 'BTC_USD', 'bid', session=poloniex.session, expire=time.time()+60)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        oorder = get_orders(oid=order.id, session=poloniex.session)
        countdown = 1000
        while oorder[0].state == 'pending' and countdown > 0:
            countdown -= 1
            oorder = get_orders(oid=order.id, session=poloniex.session)
            if oorder[0].state == 'pending':
                time.sleep(0.01)
                poloniex.session.close()

        assert len(oorder) == 1
        assert oorder[0].state == 'open'
        print oorder[0].order_id
        poloniex.session.close()
        cancel_orders('poloniex', order_id=oorder[0].order_id)
        corder = get_order_by_order_id(oorder[0].order_id, 'poloniex', poloniex.session)
        countdown = 1000
        while (corder is None or corder.state != 'closed') and countdown > 0:
            countdown -= 1
            corder = get_order_by_order_id(oorder[0].order_id, 'poloniex', poloniex.session)
            if (corder is None or corder.state != 'closed'):
                time.sleep(0.01)
                poloniex.session.close()

        assert corder.state == 'closed'

    def test_cancel_order_order_id_no_prefix(self):
        poloniex.sync_orders()
        order = create_order('poloniex', 100, 0.1, 'BTC_USD', 'bid', session=poloniex.session, expire=time.time()+60)
        assert isinstance(order.id, int)
        assert isinstance(order.price, Amount)
        assert order.price == Amount("100 USD")
        assert order.state == 'pending'
        oorder = get_orders(oid=order.id, session=poloniex.session)
        countdown = 1000
        while oorder[0].state == 'pending' and countdown > 0:
            countdown -= 1
            oorder = get_orders(oid=order.id, session=poloniex.session)
            if oorder[0].state == 'pending':
                time.sleep(0.01)
                poloniex.session.close()

        assert len(oorder) == 1
        assert oorder[0].state == 'open'
        print oorder[0].order_id.split("|")[1]
        cancel_orders('poloniex', order_id=oorder[0].order_id.split("|")[1])
        #corder = get_orders(oid=order.id, session=poloniex.session)
        corder = get_order_by_order_id(oorder[0].order_id, 'poloniex', poloniex.session)
        countdown = 1000
        while (corder is None or corder.state != 'closed') and countdown > 0:
            countdown -= 1
            #corder = get_orders(oid=order.id, session=poloniex.session)
            corder = get_order_by_order_id(oorder[0].order_id, 'poloniex', poloniex.session)
            if (corder is None or corder.state != 'closed'):
                time.sleep(0.01)
                poloniex.session.close()

        assert corder.state == 'closed'

    def test_cancel_orders_by_market(self):
        poloniex.sync_orders()
        assert create_order('poloniex', 100, 0.1, 'BTC_USD', 'bid', session=poloniex.session, expire=time.time()+60) is not None
        last = create_order('poloniex', 100, 0.1, 'BTC_USD', 'bid', session=poloniex.session, expire=time.time() + 60)
        got = get_order_by_order_id(last.order_id, 'poloniex', session=poloniex.session)
        countdown = 1000
        while (got is None or got.state != 'open') and countdown > 0:
            countdown -= 1
            got = get_order_by_order_id(last.order_id, 'poloniex', session=poloniex.session)
            time.sleep(0.01)
            poloniex.session.close()
        obids = len(get_orders(side='bid', state='open', session=poloniex.session))
        assert obids >= 2
        assert create_order('poloniex', 1000, 0.1, 'BTC_USD', 'ask', session=poloniex.session, expire=time.time()+60) is not None
        assert create_order('poloniex', 1000, 0.1, 'BTC_USD', 'ask', session=poloniex.session, expire=time.time()+60) is not None
        last = create_order('poloniex', 1000, 0.1, 'ETH_BTC', 'ask', session=poloniex.session, expire=time.time()+60)
        got = get_order_by_order_id(last.order_id, 'poloniex', session=poloniex.session)
        countdown = 1000
        while (got is None or got.state != 'open') and countdown > 0:
            countdown -= 1
            got = get_order_by_order_id(last.order_id, 'poloniex', session=poloniex.session)
            time.sleep(0.01)
            poloniex.session.close()
        oasks = len(get_orders(side='ask', state='open', exchange='poloniex', session=poloniex.session))
        assert oasks >= 3
        poloniex.session.close()
        cancel_orders('poloniex', market='BTC_USD')
        bids = len(get_orders(market='BTC_USD', state='open', exchange='poloniex', session=poloniex.session))  # include pending orders? race?
        countdown = 3000
        while bids != 0 and countdown > 0:
            countdown -= 1
            bids = len(get_orders(market='BTC_USD', state='open', exchange='poloniex', session=poloniex.session))
            if bids != 0:
                time.sleep(0.01)
                poloniex.session.close()
        assert bids == 0
        cancel_orders('poloniex', market='ETH_BTC', side='ask')

    def test_cancel_orders_by_side(self):
        poloniex.sync_orders()
        assert create_order('poloniex', 100, 0.1, 'BTC_USD', 'bid', session=poloniex.session, expire=time.time()+60) is not None
        last = create_order('poloniex', 100, 0.1, 'BTC_USD', 'bid', session=poloniex.session, expire=time.time()+60)
        got = get_order_by_order_id(last.order_id, 'poloniex', session=poloniex.session)
        countdown = 1000
        while (got is None or got.state != 'open') and countdown > 0:
            countdown -= 1
            got = get_order_by_order_id(last.order_id, 'poloniex', session=poloniex.session)
            time.sleep(0.01)
            poloniex.session.close()
        obids = len(get_orders(side='bid', state='open', session=poloniex.session))
        assert obids >= 2
        assert create_order('poloniex', 1000, 0.01, 'BTC_USD', 'ask', session=poloniex.session, expire=time.time()+60) is not None
        last = create_order('poloniex', 1000, 0.01, 'BTC_USD', 'ask', session=poloniex.session, expire=time.time()+60)
        got = get_order_by_order_id(last.order_id, 'poloniex', session=poloniex.session)
        countdown = 1000
        while (got is None or got.state != 'open') and countdown > 0:
            countdown -= 1
            got = get_order_by_order_id(last.order_id, 'poloniex', session=poloniex.session)
            time.sleep(0.01)
            poloniex.session.close()
        oasks = len(get_orders(side='ask', state='open', exchange='poloniex', session=poloniex.session))
        assert oasks >= 2
        poloniex.session.close()
        cancel_orders('poloniex', side='bid')
        bids = len(get_orders(side='bid', state='open', exchange='poloniex', session=poloniex.session))  # include pending orders? race?
        countdown = 3000
        while bids != 0 and countdown > 0:
            countdown -= 1
            bids = len(get_orders(side='bid', state='open', exchange='poloniex', session=poloniex.session))
            if bids != 0:
                time.sleep(0.01)
                poloniex.session.close()
        asks = len(get_orders(side='ask', state='open', exchange='poloniex', session=poloniex.session))
        assert asks == oasks
        assert bids == 0
        poloniex.session.close()
        cancel_orders('poloniex', side='ask')
        asks = len(get_orders(side='ask', state='open', exchange='poloniex', session=poloniex.session))
        countdown = 3000
        while asks != 0 and countdown > 0:
            countdown -= 1
            asks = len(get_orders(side='ask', state='open', exchange='poloniex', session=poloniex.session))
            if asks != 0:
                time.sleep(0.01)
                poloniex.session.close()
        assert asks == 0

    def test_sync_trades(self):
        try:
            poloniex.session.delete(poloniex.session.query(em.Trade).filter(em.Trade.exchange == 'poloniex').first())
            poloniex.session.commit()
            poloniex.session.close()
        except:
            pass
        trades = len(get_trades('poloniex', session=poloniex.session))
        poloniex.session.close()
        sync_trades('poloniex', rescan=True)
        newtrades = len(get_trades('poloniex', session=poloniex.session))
        countdown = 100 * 60 * 60 * 3  # 3 hours
        while newtrades == trades and countdown > 0:
            countdown -= 1
            newtrades = len(get_trades('poloniex', session=poloniex.session))
            if newtrades == trades:
                time.sleep(0.01)
                poloniex.session.close()

        assert newtrades > trades

    def test_sync_credits(self):
        try:
            poloniex.session.delete(poloniex.session.query(wm.Credit).filter(wm.Credit.network == 'poloniex').first())
            poloniex.session.commit()
            poloniex.session.close()
        except:
            pass
        credits = len(get_credits('poloniex', session=poloniex.session))
        sync_credits('poloniex', rescan=True)
        poloniex.session.close()
        newcreds = len(get_credits('poloniex', session=poloniex.session))
        countdown = 100 * 60 * 30  # half hour
        while newcreds == credits and countdown > 0:
            countdown -= 1
            newcreds = len(get_credits('poloniex', session=poloniex.session))
            if newcreds == credits:
                time.sleep(0.01)
                poloniex.session.close()
        assert newcreds > credits

    def test_sync_debits(self):
        try:
            poloniex.session.delete(poloniex.session.query(wm.Debit).filter(wm.Debit.network == 'poloniex').first())
            poloniex.session.commit()
            poloniex.session.close()
        except:
            pass
        debits = len(get_debits('poloniex', session=poloniex.session))
        sync_debits('poloniex', rescan=True)
        poloniex.session.close()
        newdebs = len(get_debits('poloniex', session=poloniex.session))
        countdown = 100 * 60 * 30  # half hour
        while newdebs == debits and countdown > 0:
            countdown -= 1
            newdebs = len(get_debits('poloniex', session=poloniex.session))
            if newdebs == debits:
                time.sleep(0.01)
                poloniex.session.close()
        assert newdebs > debits

    def test_ticker(self):
        sync_ticker('poloniex', 'BTC_USD')
        ticker = get_ticker('poloniex', 'BTC_USD')
        countdown = 1000
        while (ticker is None or len(ticker) == 0) and countdown > 0:
            countdown -= 1
            ticker = get_ticker('poloniex', 'BTC_USD')
            if ticker is None:
                time.sleep(0.01)
        tick = json.loads(ticker)
        assert validate(tick, SCHEMAS['Ticker']) is None
