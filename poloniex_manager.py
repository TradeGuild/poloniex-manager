"""
Plugin for managing a Poloniex account.
This module can be imported by trade_manager and used like a plugin.
"""
import datetime
import hmac
import json
import time
import urllib
from requests import Timeout

from ledger import Amount
from ledger import Balance

from requests.packages.urllib3.connection import ConnectionError

from sqlalchemy_models import jsonify2
from sqlalchemy_models.util import filter_query_by_attr

import hashlib
import requests

from trade_manager import em, wm
from trade_manager.plugin import ExchangePluginBase, get_order_by_order_id, submit_order, get_orders

baseUrl = 'https://poloniex.com/public?command='
privUrl = 'https://poloniex.com/tradingApi'

REQ_TIMEOUT = 10  # seconds


class Poloniex(ExchangePluginBase):
    NAME = 'poloniex'
    _user = None

    def submit_private_request(self, method, params=None, retry=0):
        """Submit request to Poloniex"""
        if params is None:
            params = {}
        params['command'] = method
        params['nonce'] = int(time.time() * 1000)
        data = urllib.urlencode(params)
        sign = hmac.new(self.secret, data, hashlib.sha512).hexdigest()
        headers = {
            'Sign': sign,
            'Key': self.key
        }
        # self.logger.debug('sending to %s\nheaders: %s\ndata: %s' % (privUrl, headers, params))
        try:
            response = json.loads(requests.post(url=privUrl, data=params,
                                  headers=headers, timeout=REQ_TIMEOUT).text)
        except (ConnectionError, Timeout, ValueError) as e:
            self.logger.exception(e)
        if "Invalid nonce" in response and retry < 3:
            return self.submit_private_request(method, params=params, retry=retry + 1)
        else:
            return response

    def submit_public_request(self, method, params=None):
        params = params if params is not None else {}
        if 'currencyPair' in params:
            method += '&currencyPair=' + str(params['currencyPair'])
        try:
            ret = requests.get(baseUrl + method, timeout=REQ_TIMEOUT)
        except (ConnectionError, Timeout) as e:
            self.logger.exception(e)
        return json.loads(ret.text)

    @classmethod
    def format_market(cls, market):
        """
        The default market symbol is an uppercase string consisting of the base commodity
        on the left and the quote commodity on the right, separated by an underscore.

        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.

        poloniex confuses base and quote currency, and uses non-standard USD.

        formatted : unformatted
        'BTC_USDT': 'USDT_BTC',
        'DASH_BTC': 'BTC_DASH',
        'DASH_USDT': 'USDT_DASH'

        :return: a market formatted according to what trade_manager expects.
        """
        market = market.upper()
        if 'USDT' in market:
            market = market.replace('USDT', 'USD')
        return "{1}_{0}".format(*market.split("_"))

    @classmethod
    def unformat_market(cls, market):
        """
        Reverse format a market to the format recognized by the exchange.
        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.

        poloniex confuses base and quote currency, and uses non-standard USD.

        formatted : unformatted
        'BTC_USDT': 'USDT_BTC',
        'DASH_BTC': 'BTC_DASH',
        'DASH_USDT': 'USDT_DASH'

        :return: a market formated according to what poloniex expects.
        """
        if 'USD' in market and not 'USDT' in market:
            market = market.replace('USD', 'USDT')
        return "{1}_{0}".format(*market.split("_"))

    @classmethod
    def format_commodity(cls, c):
        """
        The default commodity symbol is an uppercase string of 3 or 4 letters.

        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.
        """
        return c if c != 'USDT' else 'USD'

    @classmethod
    def unformat_commodity(cls, c):
        """
        Reverse format a commodity to the format recognized by the exchange.
        If the data provided by the exchange does not match the default
        implementation, then this method must be re-implemented.
        """
        return c if c != 'USD' else 'USDT'

    @classmethod
    def sync_book(cls, market=None):
        pass

    def sync_ticker(self, market='BTC_USD'):
        self.logger.debug("getting poloniex %s market" % market)
        pair = self.unformat_market(market)
        self.logger.debug("getting poloniex %s pair" % pair)
        full_ticker = self.submit_public_request('returnTicker')
        self.logger.debug("poloniex %s full_ticker %s" % (market, full_ticker))
        ticker = full_ticker[pair]
        self.logger.debug("poloniex %s ticker %s" % (market, ticker))
        tick = em.Ticker(float(ticker['highestBid']),
                         float(ticker['lowestAsk']),
                         float(ticker['high24hr']),
                         float(ticker['low24hr']),
                         float(ticker['quoteVolume']),
                         float(ticker['last']),
                         market, 'poloniex')
        self.logger.debug("poloniex %s tick %s" % (market, tick))
        jtick = jsonify2(tick, 'Ticker')
        self.logger.debug("poloniex %s json ticker %s" % (market, jtick))
        self.red.set('poloniex_%s_ticker' % market, jtick)
        return tick

    def sync_balances(self):
        data = self.submit_private_request('returnCompleteBalances')
        # self.logger.debug("balances data: %s" % data)
        available = Balance()
        total = Balance()
        for comm in data:
            # self.logger.debug("comm: %s" % comm)
            commodity = self.format_commodity(comm)
            aamount = Amount("{0:.8f} {1}".format(float(data[comm]['available']), commodity))
            available = available + aamount
            total = total + aamount + Amount("{0:.8f} {1}".format(float(data[comm]['onOrders']), commodity))
        self.logger.debug("total balance: %s" % total)
        self.logger.debug("available balance: %s" % available)
        bals = {}
        for amount in total:
            comm = str(amount.commodity)
            bals[comm] = self.session.query(wm.Balance).filter(wm.Balance.user_id == self.manager_user.id) \
                .filter(wm.Balance.currency == comm).one_or_none()
            if not bals[comm]:
                bals[comm] = wm.Balance(amount, available.commodity_amount(amount.commodity), comm, "",
                                        self.manager_user.id)
                self.session.add(bals[comm])
            else:
                bals[comm].load_commodities()
                bals[comm].total = amount
                bals[comm].available = available.commodity_amount(amount.commodity)
        try:
            self.session.commit()
        except Exception as e:
            self.logger.exception(e)
            self.session.rollback()
            self.session.flush()

    def sync_orders(self):
        oorders = self.get_open_orders()
        dboorders = get_orders(exchange='poloniex', state='open', session=self.session)
        for dbo in dboorders:
            if dbo not in oorders:
                dbo.state = 'closed'
        self.session.commit()

    @classmethod
    def get_order_book(cls, market='BTC_USD'):
        market = cls.unformat_market(market)
        book = cls.submit_public_request('Depth', {'pair': market})
        return book['result'][market]

    # private methods
    def cancel_order(self, oid=None, order_id=None, order=None):
        if order is None and oid is not None:
            order = self.session.query(em.LimitOrder).filter(em.LimitOrder.id == oid).first()
        elif order is None and order_id is not None:
            order = self.session.query(em.LimitOrder).filter(em.LimitOrder.order_id == order_id).first()
        elif order is None:
            return
        resp = self.submit_private_request('cancelOrder', {'orderNumber': order.order_id.split("|")[1]})
        if resp and 'success' in resp:
            order.state = 'closed'
            order.order_id = order.order_id.replace('tmp', 'poloniex')
            try:
                self.session.commit()
            except Exception as e:
                self.logger.exception(e)
                self.session.rollback()
                self.session.flush()

    def cancel_orders(self, market=None, side=None, oid=None, order_id=None):
        if oid is not None or order_id is not None:
            order = self.session.query(em.LimitOrder)
            if oid is not None:
                order = order.filter(em.LimitOrder.id == oid).first()
            elif order_id is not None:
                order_id = order_id if "|" not in order_id else "poloniex|%s" % order_id.split("|")[1]
                order = get_order_by_order_id(order_id, 'poloniex', session=self.session)
            self.cancel_order(order=order)
        else:
            orders = self.get_open_orders(market=market)
            for o in orders:
                if market is not None and market != o.market:
                    continue
                if side is not None and side != o.side:
                    continue
                self.cancel_order(order=o)

    def create_order(self, oid, expire=None):
        order = self.session.query(em.LimitOrder).filter(em.LimitOrder.id == oid).first()
        if not order:
            self.logger.warning("unable to find order %s" % oid)
            if expire is not None and expire < time.time():
                submit_order('poloniex', oid, expire=expire)  # back of the line!
            return
        market = self.unformat_market(order.market)
        amount = str(order.amount.number()) if isinstance(order.amount, Amount) else str(order.amount)
        price = str(order.price.number()) if isinstance(order.price, Amount) else str(order.price)
        side = 'buy' if order.side == 'bid' else 'sell'
        options = {'amount': amount, 'rate': price, 'currencyPair': market}
        resp = None
        try:
            resp = self.submit_private_request(side, options)
        except Exception as e:
            self.logger.exception(e)
        # self.logger.debug("create order resp %s" % resp)
        if resp is None or 'error' in resp and len(resp['error']) > 0:
            self.logger.warning('poloniex unable to create order %r for reason %r' % (options, resp))
            # Do nothing. The order can stay locally "pending" and be retried, if desired.
        elif 'orderNumber' in resp:
            order.order_id = 'poloniex|%s' % resp['orderNumber']
            order.state = 'open'
            self.logger.debug("submitted order %s" % order)
            try:
                self.session.commit()
            except Exception as e:
                self.logger.exception(e)
                self.session.rollback()
                self.session.flush()
            return order

    def get_open_orders(self, market=None):
        pair = 'all' if market is None else self.unformat_market(market)
        oorders = self.submit_private_request('returnOpenOrders', {'currencyPair': pair})
        # self.logger.debug('open orders %s' % oorders)
        orders = []

        def handle_market_orders(mppair, mporders):
            for porder in mporders:
                side = 'ask' if porder['type'] == 'sell' else 'bid'
                pair = self.format_market(mppair)
                base = self.base_commodity(pair)
                amount = Amount("%s %s" % (porder['amount'], base))
                quote = self.quote_commodity(pair)
                try:
                    lo = get_order_by_order_id(porder['orderNumber'], 'poloniex', session=self.session)
                except Exception as e:
                    self.logger.exception(e)
                if lo is None:
                    lo = em.LimitOrder(Amount("%s %s" % (porder['rate'], quote)), amount, pair, side,
                                       self.NAME, porder['orderNumber'], exec_amount=Amount("0 %s" % base),
                                       state='open')
                    self.session.add(lo)
                else:
                    lo.state = 'open'
                orders.append(lo)

        if len(oorders) == 0:
            return []
        elif market is None:
            for ppair in oorders:
                handle_market_orders(ppair, oorders[ppair])
        else:
            handle_market_orders(pair, oorders)
        try:
            self.session.commit()
        except Exception as e:
            self.logger.exception(e)
            self.session.rollback()
            self.session.flush()
        return orders

    def get_trades_history(self, begin=None, tend=None, market=None):
        params = {'currencyPair': 'all' if market is None else self.unformat_market(market)
                  }
        if begin is not None:
            params['start'] = str(int(begin))
        if tend is not None:
            params['end'] = str(int(tend))
        return self.submit_private_request('returnTradeHistory', params)

    def sync_trades(self, market=None, rescan=False):
        tend = time.time()
        lastend = tend - 1
        lastsleep = 4
        allknown = False
        changed = False
        this = self

        def handle_trades(pair, trades, tend):
            changed = False
            for row in trades:
                ftime = time.mktime(time.strptime(row['date'], "%Y-%m-%d %H:%M:%S"))
                dtime = datetime.datetime.fromtimestamp(ftime)
                if ftime < tend:
                    tend = ftime
                    this.logger.info("new tend! %s" % tend)
                found = this.session.query(em.Trade) \
                    .filter(em.Trade.trade_id == 'poloniex|%s' % row['globalTradeID']) \
                    .count()
                if found != 0:
                    this.logger.debug("%s already known" % row['globalTradeID'])
                    continue
                # market = self.format_market(row['pair'])
                price = float(row['rate'])
                amount = float(row['amount'])
                fee = float(row['fee'])
                feeside = 'quote'  # TODO this is wrong! port from old ledger function
                side = row['type']
                trade = em.Trade(row['globalTradeID'], 'poloniex', pair, side, amount, price, fee,
                                 feeside, dtime)
                this.logger.debug("trade: %s" % trade)
                this.session.add(trade)
                changed = True
            return tend, changed

        while tend != lastend:
            lastend = tend
            try:
                trades = self.get_trades_history(market=market, tend=tend)
                lastsleep *= 0.95
            except (IOError, ValueError) as e:
                if "ReadTimeout" in str(e):
                    lastsleep *= 2
                    time.sleep(lastsleep)
                    continue
                return
            if len(trades) == 0:
                break
            elif market is None:
                for pair in trades:
                    tend, nchanged = handle_trades(pair=self.format_market(pair), trades=trades[pair], tend=tend)
                    changed = True if nchanged else changed
            else:
                tend, nchanged = handle_trades(pair=market, trades=trades, tend=tend)
                changed = True if nchanged else changed
            if not rescan:
                break
        if changed:
            self.session.commit()

    def get_ledgers(self, begin=None, tend=None):
        params = {}
        if begin is not None:
            params['start'] = str(begin)
        else:
            params['start'] = str(1389728364)  # Poloniex founded Jan 2014
        if tend is not None:
            params['end'] = str(tend)
        else:
            params['end'] = str(time.time())
        self.logger.debug("get dw params %s" % params)
        return self.submit_private_request('returnDepositsWithdrawals', params)

    def sync_credits(self, rescan=False):
        tend = time.time()
        lastend = tend - 1
        lastsleep = 2
        changed = False

        while tend != lastend:
            lastend = tend
            try:
                ledgers = self.get_ledgers(tend=tend)
                lastsleep *= 0.95
                self.logger.debug(ledgers)
            except (IOError, ValueError) as e:
                self.logger.exception(e)
                if "ReadTimeout" in str(e):
                    lastsleep *= 2
                    time.sleep(lastsleep)
                    continue
                return

            if len(ledgers) == 0:
                break
            for row in ledgers['deposits']:
                if tend < float(row['timestamp']) and rescan:
                    tend = float(row['timestamp'])
                found = self.session.query(wm.Credit) \
                    .filter(wm.Credit.ref_id == 'poloniex|%s' % row['txid']) \
                    .count()
                if found != 0:
                    self.logger.debug("%s already known" % row['txid'])
                    continue
                self.logger.debug("%s not known" % row['txid'])
                dtime = datetime.datetime.fromtimestamp(float(row['timestamp']))
                asset = self.format_commodity(row['currency'])
                amount = Amount("%s %s" % (row['amount'], asset))
                refid = row['txid']
                cred = wm.Credit(amount, row['address'], asset, "poloniex", "complete", refid,
                                 "poloniex|%s" % row['txid'],
                                 self.manager_user.id, dtime)
                self.logger.debug("cred: %s" % cred)
                self.session.add(cred)
                changed = True
            for row in ledgers['withdrawals']:
                if tend < float(row['timestamp']) and rescan:
                    tend = float(row['timestamp'])
                found = self.session.query(wm.Credit) \
                    .filter(wm.Credit.ref_id == 'poloniex|%s' % row['withdrawalNumber']) \
                    .count()
                if found != 0:
                    self.logger.debug("%s already known" % row['withdrawalNumber'])
                    continue
                self.logger.debug("%s not known" % row['withdrawalNumber'])
                dtime = datetime.datetime.fromtimestamp(float(row['timestamp']))
                asset = self.format_commodity(row['currency'])
                amount = Amount("%s %s" % (row['amount'], asset))
                refid = row['status']
                deb = wm.Debit(amount, Amount("0 %s" % asset), row['address'], asset, "poloniex", "complete", refid,
                               "poloniex|%s" % row['withdrawalNumber'],
                               self.manager_user.id, dtime)
                self.logger.debug("deb: %s" % deb)
                self.session.add(deb)
                changed = True
        self.logger.debug("changed? %s" % changed)
        if changed:
            self.session.commit()

    sync_debits = sync_credits


def main():
    poloniex = Poloniex()
    poloniex.run()


if __name__ == "__main__":
    main()
