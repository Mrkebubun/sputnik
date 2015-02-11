# Copyright (c) 2014, Mimetic Markets, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

### UI API ###

if module?
    autobahn = require "autobahn"
    EventEmitter = require("./events").EventEmitter
    CryptoJS = require "crypto-js"
else
    EventEmitter = window.EventEmitter
    autobahn = window.autobahn
    CryptoJS = window.CryptoJS

class @Sputnik extends EventEmitter

    markets: {}

    orders: {}
    positions: {}
    margins: {}
    subscriptions: {}
    authenticated: false
    profile:
        email: null
        nickname: null
        audit_secret: null
        locale: null
    chat_messages: []
    connected: false
    log_flag: false

    constructor: (@uri) ->
        # Initialize globalization settings

    ### Sputnik API  ###

    # network control

    connect: () =>
        @connection = new autobahn.Connection
            url: @uri
            realm: "sputnik"
            authmethods: ["anonymous"]
        @connection.onopen = @onOpen
        @connection.onclose = @onClose

        @connection.open()

        setTimeout () =>
            if not @connected
                @connection.open()
        , 30000

    close: () =>
        @connection?.close()
        @connection = null
        @session = null

    # market selection

    encode_market: (market) =>
        market.replace('/', '_').toLowerCase()

    follow: (market) =>
        market_encoded = @encode_market market
        @subscribe "feeds.market.book.#{market_encoded}", @onBook
        @subscribe "feeds.market.trades.#{market_encoded}", @onTrade
        @subscribe "feeds.market.safe_prices.#{market_encoded}", @onSafePrice
        @subscribe "feeds.market.ohlcv.#{market_encoded}", @onOHLCV
        @following = market

    unfollow: (market) =>
        market_encoded = @encode_market market
        @unsubscribe "feeds.market.book.#{market_encoded}"
        @unsubscribe "feeds.market.trades.#{market_encoded}"
        @unsubscribe "feeds.market.safe_prices.#{market_encoded}"
        @unsubscribe "feeds.market.ohlcv.#{market_encoded}"
        @following = undefined

    # authentication and account management

    computeHash: (password) =>
        @log "Computing password hash..."
        salt = Math.random().toString(36).slice(2)
        @authextra =
            salt: salt
            iterations: 1000
        key = autobahn.auth_cra.derive_key password, @authextra.salt
        return [key, salt]

    makeAccount: (username, secret, email, nickname, locale) =>
        [key, salt] = @computeHash secret

        @call("rpc.registrar.make_account", username, "#{salt}:#{key}", email, nickname, locale).then \
            (result) =>
                @emit "make_account_success", result
            , (error) =>
                @emit "make_account_fail", error

    getProfile: () =>
        @call("rpc.trader.get_profile").then (@profile) =>
            @emit "profile", @profile

    changeProfile: (profile) =>
        @call("rpc.trader.change_profile", profile).then (@profile) =>
            @log ["profile_changed", @profile]
            @emit "profile", @profile
            @emit "change_profile_success", @profile

    getAudit: () =>
        @call("rpc.info.get_audit").then (wire_audit_details) =>
            @log ["audit_details", wire_audit_details]
            audit_details = @copy(wire_audit_details)
            for side in [audit_details.liabilities, audit_details.assets]
                for ticker, data of side
                    data.total = @quantityFromWire(ticker, data.total)
                    for position in data.positions
                        position[1] = @quantityFromWire(ticker, position[1])

            @emit "audit_details", audit_details
            @emit "audit_hash", @getAuditHash(wire_audit_details.timestamp)

    getPermissions: () =>
        @call("rpc.trader.get_permissions").then (permissions) =>
            @log ["permissions", permissions]
            @emit "permissions", permissions

    getAuditHash: (timestamp) =>
        secret = @profile.audit_secret
        username = @username
        email = @profile.email
        nickname = @profile.nickname
        string = "#{secret}:#{username}:#{nickname}:#{email}:#{timestamp}"
        return CryptoJS.MD5(string).toString(CryptoJS.enc.Base64)

    getTransactionHistory: (start_timestamp, end_timestamp) =>
        @call("rpc.trader.get_transaction_history", start_timestamp, end_timestamp).then (wire_transaction_history) =>
            @log ["Transaction history", wire_transaction_history]
            transaction_history = []
            for transaction in wire_transaction_history
                transaction_history.push @transactionFromWire(transaction)
            @emit "transaction_history", transaction_history

    processHash: () =>
        if window?
            hash = window.location.hash.substring(1).split('&')
            @log ["Hash", hash]
            args = {}
            for entry in hash
                pair = entry.split(/\=(.+)?/)
                key = decodeURIComponent(pair[0])
                value = decodeURIComponent(pair[1])
                @log [entry, pair, key, value]
                args[key] = value

            @log ["args", args]

            if args.function?
                if args.function == 'change_password_token'
                    @cp_args = args
                    @emit args.function, args

    authenticate: (@username, password) =>
        if not @session?
            @wtf "Not connected."

        @rejoin = [@username, ["wampcra"]]
        @log ["rejoin", @rejoin]

        @session._onchallenge = (session, method, extra) =>
            @log ["challenge", method, extra]
            if method == "wampcra"
                @authextra = extra
                key = autobahn.auth_cra.derive_key password, extra.salt
                autobahn.auth_cra.sign key, extra.challenge

        @session.leave "sputnik.internal.rejoin"

    restoreSession: (@username, uid) =>
        if not @session?
            @wtf "Not connected."

        @log "Attempting cookie login"
        @rejoin = [@username, ["cookie"]]

        @session._onchallenge = (session, method, extra) =>
            if method == "cookie"
                @authextra = extra
                uid

        @session.leave "sputnik.internal.rejoin"

    changePasswordToken: (new_password) =>
        if not @session?
            @wtf "Not connected."

        @log "Changing password with token"
        [key, salt] = @computeHash(new_password)

        @call("rpc.registrar.change_password_token", @cp_args.username, "#{salt}:#{key}", @cp_args.token).then \
            (message) =>
                @log "password change successfully"
                @emit "change_password_token_success", @cp_args.username
            , (error) =>
                @error "password change error", error
                @emit "change_password_token_fail", error

    changePassword: (old_password, new_password) =>
        if not @authenticated
            @wtf "Not logged in."

        salt = @authextra.salt
        old_secret = autobahn.auth_cra.derive_key old_password, salt
        new_secret = autobahn.auth_cra.derive_key new_password, salt

        @call("rpc.token.change_password", "#{salt}:#{old_secret}", "#{salt}:#{new_secret}").then \
            (message) =>
                @log "password changed successfully"
                @emit "change_password_success", message
            , (error) =>
                @error ["password change error", error]
                @emit "change_password_fail", error

    getResetToken: (username) =>
        @call("rpc.registrar.get_reset_token", username).then \
            (success) =>
                @emit "get_reset_token_success", success
            , (error) =>
                @emit "get_reset_token_fail", error

    getRequestSupportNonce: (type, success, error) =>
        @call("rpc.trader.request_support_nonce", type).then success, error

    logout: () =>
        @authenticated = false
        @call "rpc.token.logout"
        @close()
        @emit "logout"
        # Reconnect after logout
        @connect()

    getCookie: () =>
        @call("rpc.token.get_cookie").then \
            (uid) =>
                @log "cookie: " + uid
                @emit "cookie", uid

    encode_username: (username) =>
        CryptoJS.SHA256(username).toString(CryptoJS.enc.Hex)

    # data conversion

    cstFromTicker: (ticker) =>
        if not ticker of @markets
            # Spit out some debugging, this should not happen
            @error ["cstFromTicker: ticker not in markets", ticker]
        contract = @markets[ticker]
        if not contract?
            @error ["cstFromTicker: contract undefined", ticker]
        if contract.contract_type is "cash_pair"
            source = @markets[contract.denominated_contract_ticker]
            target = @markets[contract.payout_contract_ticker]
        else if contract.contract_type in ["prediction", "futures"]
            source = @markets[contract.denominated_contract_ticker]
            target = @markets[ticker]
        else
            source = @markets[ticker]
            target = @markets[ticker]

        return [contract, source, target]

    copy: (object) =>
        new_object = {}
        for key of object
            new_object[key] = object[key]
        return new_object

    ohlcvFromWire: (wire_ohlcv) =>
        ticker = wire_ohlcv['contract']
        ohlcv =
            contract: ticker
            open: @priceFromWire(ticker, wire_ohlcv['open'])
            high: @priceFromWire(ticker, wire_ohlcv['high'])
            low: @priceFromWire(ticker, wire_ohlcv['low'])
            close: @priceFromWire(ticker, wire_ohlcv['close'])
            volume: @quantityFromWire(ticker, wire_ohlcv['volume'])
            vwap: @priceFromWire(ticker, wire_ohlcv['vwap'])
            open_timestamp: wire_ohlcv['open_timestamp']
            close_timestamp: wire_ohlcv['close_timestamp']
            period: wire_ohlcv.period
        return ohlcv

    positionFromWire: (wire_position) =>
        ticker = wire_position.contract
        position = @copy(wire_position)
        position.position = @quantityFromWire(ticker, wire_position.position)
        if @markets[ticker].contract_type is "futures"
            position.reference_price = @priceFromWire(ticker, wire_position.reference_price)
        return position

    orderToWire: (order) =>
        ticker = order.contract
        wire_order = @copy(order)
        wire_order.price = @priceToWire(ticker, order.price)
        wire_order.quantity = @quantityToWire(ticker, order.quantity)
        if order.quantity_left?
            wire_order.quantity_left = @quantityToWire(ticker, order.quantity_left)
        return wire_order

    orderFromWire: (wire_order) =>
        ticker = wire_order.contract
        order = @copy(wire_order)
        order.price = @priceFromWire(ticker, wire_order.price)
        order.quantity = @quantityFromWire(ticker, wire_order.quantity)
        order.quantity_left = @quantityFromWire(ticker, wire_order.quantity_left)
        order.timestamp = wire_order.timestamp
        return order

    bookRowFromWire: (ticker, wire_book_row) =>
        book_row = @copy(wire_book_row)
        book_row.price = @priceFromWire(ticker, wire_book_row.price)
        book_row.quantity = @quantityFromWire(ticker, wire_book_row.quantity)
        return book_row

    tradeFromWire: (wire_trade) =>
        ticker = wire_trade.contract
        trade = @copy(wire_trade)
        trade.price = @priceFromWire(ticker, wire_trade.price)
        trade.quantity = @quantityFromWire(ticker, wire_trade.quantity)
        trade.timestamp = wire_trade.timestamp
        return trade

    fillFromWire: (wire_fill) =>
        ticker = wire_fill.contract
        fill = @copy(wire_fill)
        fill.fees = @copy(wire_fill.fees)
        fill.price = @priceFromWire(ticker, wire_fill.price)
        fill.quantity = @quantityFromWire(ticker, wire_fill.quantity)
        fill.timestamp = wire_fill.timestamp
        for fee_ticker, fee of wire_fill.fees
            fill.fees[fee_ticker] = @quantityFromWire(fee_ticker, fee)
        return fill

    transactionFromWire: (wire_transaction) =>
        transaction = @copy(wire_transaction)
        ticker = wire_transaction.contract
        transaction.quantity = @quantityFromWire(ticker, wire_transaction.quantity)
        transaction.timestamp = wire_transaction.timestamp
        if transaction.balance?
            transaction.balance = @quantityFromWire(ticker, wire_transaction.balance)
        return transaction

    checkPriceValidity: (ticker, price) =>
        if price != @priceFromWire(ticker, @priceToWire(ticker, price))
            return false
        else if @markets[ticker].contract_type == "prediction" and price > 1
            return false
        else if price <= 0
            return false
        else
            return true

    checkQuantityValidity: (ticker, quantity) =>
        if quantity != @quantityFromWire(ticker, @quantityToWire(ticker, quantity))
            return false
        else if quantity <= 0
            return false
        else
            return true

    quantityToWire: (ticker, quantity) =>
        [contract, source, target] = @cstFromTicker(ticker)

        if contract.contract_type in ["prediction", "futures"]
            # Prediction contracts always have integer quantity
            quantity = quantity - quantity % 1
        else
            quantity = quantity * target.denominator
            if contract.contract_type != "cash"
                quantity = quantity - quantity % contract.lot_size

        return quantity

    priceToWire: (ticker, price) =>
        [contract, source, target] = @cstFromTicker(ticker)
        if contract.contract_type in ["prediction", "futures"]
            price = Math.round(price * contract.denominator)
        else
            price = Math.round(price * source.denominator * contract.denominator)

        price = price - price % contract.tick_size
        return price

    quantityFromWire: (ticker, quantity) =>
        [contract, source, target] = @cstFromTicker(ticker)
        if contract.contract_type in ["prediction", "futures"]
            return quantity
        else
            return quantity / target.denominator

    priceFromWire: (ticker, price) =>
        [contract, source, target] = @cstFromTicker(ticker)
        if contract.contract_type in ["prediction", "futures"]
            return price / contract.denominator
        else
            return price / (source.denominator * contract.denominator)

    cashSpentFromWire: (cash_spent_wire) =>
        cash_spent = @copy(cash_spent_wire)
        for ticker, cash of cash_spent
            cash_spent[ticker] = @quantityFromWire(ticker, cash)

        return cash_spent

    safePricesFromWire: (safe_prices_wire) =>
        safe_prices = @copy(safe_prices_wire)
        for ticker, price of safe_prices
            @warn [ticker, price]
            safe_prices[ticker] = @priceFromWire(ticker, price)
        @warn [safe_prices]
        return safe_prices

    getPricePrecision: (ticker) =>
        [contract, source, target] = @cstFromTicker(ticker)

        if contract.contract_type in ["prediction", "futures"]
            return Math.round(Math.max(Math.log(contract.denominator / contract.tick_size) / Math.LN10,0))
        else
            return Math.round(Math.max(Math.log(source.denominator * contract.denominator / contract.tick_size) / Math.LN10,0))

    getQuantityPrecision: (ticker) =>
        [contract, source, target] = @cstFromTicker(ticker)
        if contract.contract_type in ["prediction", "futures"]
            return 0
        else if contract.contract_type is "cash"
            return Math.round(Math.max(Math.log(contract.denominator / contract.lot_size) / Math.LN10,0))
        else
            return Math.round(Math.max(Math.log(target.denominator / contract.lot_size) / Math.LN10,0))

    getMinMove: (ticker) =>
        [contract, source, target] = @cstFromTicker(ticker)
        return contract.tick_size


    getPriceScale: (ticker) =>
        [contract, source, target] = @cstFromTicker(ticker)
        if contract.contract_type in ["prediction", "futures"]
            return contract.denominator
        else
            return source.denominator * contract.denominator

    # order manipulation
    canPlaceOrder: (ticker, quantity, price, side) =>
      new_order =
          quantity: quantity
          quantity_left: quantity
          price: price
          contract: ticker
          side: side
      [low_margin, high_margin, max_cash_spent] = @calculateMargin @orderToWire new_order
      cash_position = @positions["BTC"].position
      return high_margin <= cash_position

    placeOrder: (ticker, quantity, price, side) =>
        order =
            quantity: quantity
            price: price
            contract: ticker
            side: side
        @log ["placing order", order]
        @call("rpc.trader.place_order", @orderToWire(order)).then \
            (res) =>
                @emit "place_order_success", res
            , (error) =>
                @emit "place_order_fail", error

    # Get the best price we think we can execute a given quantity
    priceForQuantity: (ticker, quantity, side) =>
        if side == 'BUY'
            book = @markets[ticker].asks
        else
            book = @markets[ticker].bids

        if isNaN quantity or quantity == 0
            if book[0]?
                return @priceFromWire(book[0].price)
            else
                if side == 'BUY'
                    return Infinity
                else
                    return 0

        quantity_wire = @quantityToWire(ticker, quantity)
        sum = 0
        for level in book
            sum += level.quantity
            if sum >= quantity_wire
                return @priceFromWire(ticker, level.price)

        if side == 'BUY'
            return Infinity
        else
            return 0


    cancelOrder: (id) =>
        @log "cancelling: #{id}"
        @call("rpc.trader.cancel_order", id).then \
            (res) =>
                @emit "cancel_order_success", res
            , (error) =>
                @emit "cancel_order_fail", error

    # deposits and withdrawals

    makeCompropagoDeposit: (store, amount, customer_email, send_sms, customer_phone, customer_phone_company) =>
        charge =
          product_price: amount
          payment_type: store
          customer_email: customer_email
          send_sms: send_sms
          customer_phone: customer_phone
          customer_phone_company: customer_phone_company
          currency: "MXN"
        @log ["compropago charge",charge]
        @call("rpc.trader.make_compropago_deposit", charge).then \
            (@ticket) =>
                @log ["compropago deposit ticket", ticket]
                @emit "compropago_deposit_success", ticket
            , (error) =>
                @error ["compropago error", error]
                @emit "compropago_deposit_fail", error

    getAddress: (contract) =>
        @call("rpc.trader.get_current_address", contract).then \
            (address) =>
                @log "address for #{contract}: #{address}"
                @emit "address", [contract, address]
            , (error) =>
                @error ["current_address_failure for #{contract}", error]
                @emit "address_fail", error

    newAddress: (contract) =>
        @call("rpc.trader.get_new_address", contract).then \
            (address) =>
                @log "new address for #{contract}: #{address}"
                @emit "address", [contract, address]
            , (error) =>
                @error ["new address failure for #{contract}", error]
                @emit "address_fail", error

    getDepositInstructions: (contract) =>
        @call("rpc.trader.get_deposit_instructions", contract).then \
            (instructions) =>
                @log "Deposit instructions for #{contract}: #{instructions}"
                @emit "deposit_instructions", [contract, instructions]

    requestWithdrawal: (ticker, amount, address) =>
        @call("rpc.trader.request_withdrawal", ticker, @quantityToWire(ticker, amount), address).then \
        (result) =>
            @log ["request_withdrawal succeeded", result]
            @emit "request_withdrawal_success", result
        , (error) =>
            @error ["request withdrawal fail", error]
            @emit "request_withdrawal_fail", error

    # account/position information
    getSafePrices: () =>
    getOpenOrders: () =>
        @call("rpc.trader.get_open_orders").then \
            (@orders) =>
                @log ["orders received", orders]
                orders = {}
                for id, order of @orders
                    if order.quantity_left > 0
                        orders[id] = @orderFromWire(order)

                @emit "orders", orders
                [low_margin, high_margin, max_cash_spent] = @calculateMargin()
                @emit "margin", [@quantityFromWire('BTC', low_margin), @quantityFromWire('BTC', high_margin)]
                @emit "cash_spent", @cashSpentFromWire(max_cash_spent)

    getPositions: () =>
        @call("rpc.trader.get_positions").then \
            (@positions) =>
                @log ["positions received", @positions]
                positions = {}
                for ticker, position of @positions
                    if @markets[ticker].contract_type != "cash_pair"
                        positions[ticker] = @positionFromWire(position)

                @emit "positions", positions
                [low_margin, high_margin, max_cash_spent] = @calculateMargin()
                @emit "margin", [@quantityFromWire('BTC', low_margin), @quantityFromWire('BTC', high_margin)]
                @emit "cash_spent", @cashSpentFromWire(max_cash_spent)

    getNewAPICredentials: () =>
        @call("rpc.token.get_new_api_credentials").then \
            (credentials) =>
                @emit "api", credentials

    openMarket: (ticker) =>
        @log "Opening market: #{ticker}"

        @getOrderBook ticker
        @getTradeHistory ticker
        @getOHLCVHistory ticker, "minute"
        @getOHLCVHistory ticker, "hour"
        @getOHLCVHistory ticker, "day"

        @follow ticker

    getOrderBook: (ticker) =>
        @call("rpc.market.get_order_book", ticker).then @onBook

    getTradeHistory: (ticker) =>
        @call("rpc.market.get_trade_history", ticker).then @onTradeHistory

    getOHLCVHistory: (ticker, period) =>
        @call("rpc.market.get_ohlcv_history", ticker, period).then @onOHLCVHistory

    ### internal methods ###

    # RPC wrapper
    call: (method, params...) =>
        if not @session?
            return @wtf "Not connected."

        if not @session.isOpen
            return @error "Session not open"

        @log ["RPC #{method}",params]
        d = @connection.defer()
        @session.call(method, params).then \
            (result) =>
                if not result.success?
                    @warn "RPC Warning: sputnik protocol violation in #{method}"
                    return d.resolve result
                if result.success
                    return d.resolve result.result
                else
                    @warn ["RPC call failed", result.error]
                    return d.reject result.error
            , (error) =>
                @wtf ["RPC Error", method, error]
        d.promise

    subscribe: (topic, callback) =>
        if not @session?
            return @wtf "Not connected."
        @log "subscribing: #{topic}"
        handler = (event) ->
            # WAMPv2 returns an array as event, we just want the first item
            callback event[0]

        @session.subscribe(topic, handler).then (subscription) =>
            if @subscriptions[topic]?
                @subscriptions[topic].push subscription
            else
                @subscriptions[topic] = [subscription]
        , (error) =>
            @emit "subscription_fail", [error, topic]

    unsubscribe: (topic) =>
        if not @session?
            return @wtf "Not connected."

        @log "unsubscribing: #{topic}"
        if @subscriptions[topic]?
            for subscription in @subscriptions[topic]
                @log ["unsubscribing", subscription]
                @session.unsubscribe subscription
            @subscriptions[topic] = []


    publish: (topic, message) =>
        if not @session?
            return @wtf "Not connected."
        @log [topic, message]
        @session.publish "#{@uri}/feeds/#{topic}", message, false

    # logging
    log: (obj) =>
        @emit "log", obj
    warn: (obj) ->
        @emit "warn", obj
    error: (obj) ->
        @emit "error", obj
    wtf: (obj) => # What a Terrible Failure
        @error obj
        @emit "wtf", obj

    # connection events
    onOpen: (@session, details) =>
        @session.onjoin = @onJoin
        @session.onleave = @onLeave
        @connected = true
        @log "Connected to #{@uri}."

        # Do initial stuff
        @processHash()

        @call("rpc.market.get_markets").then @onMarkets, @wtf
        @call("rpc.info.get_exchange_info").then @onExchangeInfo, @wtf

        @emit "open"

    onClose: (code, reason, details) =>
        @error ["Connection lost", code, reason, details]
        @connected = false
        @emit "close", [code, reason, details]

    onJoin: =>
        @log ["onJoin", @username]

        # Clear subscriptions
        @subscriptions = {}

        if @following?
            @follow @following

        if @username? and @username != null
            @log ["authenticated"]
            @authenticated = true

            @getProfile()
            @getSafePrices()
            @getOpenOrders()
            @getPositions()
            @getPermissions()

            @emit "auth_success", @username
            username_encoded = @encode_username @username

            try
                @subscribe "feeds.user.orders.#{username_encoded}", @onOrder
                @subscribe "feeds.user.fills.#{username_encoded}", @onFill
                @subscribe "feeds.user.transactions.#{username_encoded}", @onTransaction
            catch error
                @log error
        else
            @log ["joined anonymously"]

        @emit "join"

    onLeave: (reason, message) =>
        @log ["leave reason", reason, message]
        if reason == "wamp.error.not_authorized"
            @username = null
            @log @rejoin
            if @rejoin? and "cookie" in @rejoin[1]
                @error ["cookie_login_fail", message.message]
                @emit "cookie_login_fail", [message.message]
            else
                @error ["auth_fail", message.message]
                @emit "auth_fail", [message.message]

            # Rejoin anonymously
            @session.join "sputnik", ["anonymous"]
        else
            if @rejoin?
                @session.join "sputnik", @rejoin[1], @rejoin[0]
            else
                @session.join "sputnik", ["anonymous"]

    # default RPC callbacks

    onMarkets: (@markets) =>
        for ticker of markets
            @markets[ticker].trades = []
            @markets[ticker].bids = []
            @markets[ticker].asks = []
            @markets[ticker].ohlcv = {day: {}, hour: {}, minute: {}}

        @log ["Markets", @markets]
        @emit "markets", @markets

    onExchangeInfo: (@exchange_info) =>
        @log ["Exchange Info", @exchange_info]
        @emit "exchange_info", @exchange_info

    # feeds
    onBook: (book) =>
        @log ["book received", book]
        book.bids.sort (a, b) -> b.price - a.price
        book.asks.sort (a, b) -> a.price - b.price

        @markets[book.contract].bids = book.bids
        @markets[book.contract].asks = book.asks
        @emitBook book.contract

    emitBook: (ticker) =>
        ui_book = 
            bids: (@bookRowFromWire(ticker, order) for order in @markets[ticker].bids)
            asks: (@bookRowFromWire(ticker, order) for order in @markets[ticker].asks)
            contract: ticker

        @log ["ui_book", ui_book]
        @emit "book", ui_book

    # Make sure we only have the last hour of trades
    cleanTradeHistory: (ticker) =>
        now = new Date()
        an_hour_ago = new Date()
        an_hour_ago.setHours(now.getHours() - 1)
        while @markets[ticker].trades.length and @markets[ticker].trades[0].timestamp / 1000 < an_hour_ago.getTime()
            @markets[ticker].trades.shift()

    emitTradeHistory: (ticker) =>
        trade_history = {}
        trade_history[ticker] = for trade in @markets[ticker].trades
            @tradeFromWire(trade)

        @emit "trade_history", trade_history

    onTradeHistory: (trade_history) =>
        @log ["trade_history received", trade_history]
        if trade_history.length > 0
            ticker = trade_history[0].contract
            @markets[ticker].trades = trade_history
            @cleanTradeHistory(ticker)
            @emitTradeHistory(ticker)
        else
            @warn "no trades in history"


    onOHLCV: (ohlcv) =>
        @log ["ohlcv", ohlcv]
        period = ohlcv.period
        ticker = ohlcv.contract
        timestamp = ohlcv.timestamp
        @markets[ticker].ohlcv[period][timestamp] = ohlcv

        @emit "ohlcv", @ohlcvFromWire(ohlcv)

    onOHLCVHistory: (ohlcv_history) =>
        @log ["ohlcv_history received", ohlcv_history]
        timestamps = Object.keys(ohlcv_history)
        if timestamps.length
            ticker = ohlcv_history[timestamps[0]].contract
            period = ohlcv_history[timestamps[0]].period
            @markets[ticker].ohlcv[period] = ohlcv_history
            @emitOHLCVHistory(ticker, period)
        else
            @warn "ohlcv_history is empty"

    emitOHLCVHistory: (ticker, period) =>
        ohlcv = {}
        for timestamp, entry of @markets[ticker].ohlcv[period]
            ohlcv[timestamp] = @ohlcvFromWire(entry)
        @emit "ohlcv_history", ohlcv

    onTrade: (trade) =>
        @log ["Trade", trade]
        ticker = trade.contract
        @markets[ticker].trades.push trade
        @emit "trade", @tradeFromWire(trade)
        @cleanTradeHistory(ticker)
        @emitTradeHistory(ticker)

    onChat: (event) =>
        user = event[0]
        message = event[1]
        msg_txt = "#{user}: #{message}"
        @chat_messages.push msg_txt
        @log "Chat: #{msg_txt}"
        @emit "chat_history", @chat_messages
        @emit "chat", msg_txt

    # My orders get updated with orders
    onOrder: (order) =>
        @log ["Order received", order]
        @emit "order", @orderFromWire(order)

        id = order.id
        if id of @orders and (order.is_cancelled or order.quantity_left == 0)
            delete @orders[id]
        else
            if order.quantity_left > 0
                @orders[id] = order

        orders = {}
        for id, order of @orders
            if order.quantity_left > 0
                orders[id] = @orderFromWire(order)

        @emit "orders", orders

        [low_margin, high_margin, max_cash_spent] = @calculateMargin()
        @emit "margin", [@quantityFromWire('BTC', low_margin), @quantityFromWire('BTC', high_margin)]
        @emit "cash_spent", @cashSpentFromWire(max_cash_spent)

    # Fills don't update my cash, transaction feed does
    onFill: (fill) =>
        @log ["Fill received", fill]
        @emit "fill", @fillFromWire(fill)

    onTransaction: (transaction) =>
        @log ["transaction received", transaction]
        # For regular clients the only type of account is a liability
        # So we always say credit is positive
        if transaction.direction == 'credit'
            sign = 1
        else
            sign = -1

        if transaction.contract of @positions
            @positions[transaction.contract].position += sign * transaction.quantity
        else
            @positions[transaction.contract] =
                position: sign * transaction.quantity
                contract: transaction.contract

        @emit "transaction", @transactionFromWire(transaction)

        positions = {}
        for ticker, position of @positions
            positions[ticker] = @positionFromWire(position)

        @emit "positions", positions
        [low_margin, high_margin, max_cash_spent] = @calculateMargin()
        @emit "margin", [@quantityFromWire('BTC', low_margin), @quantityFromWire('BTC', high_margin)]
        @emit "cash_spent", @cashSpentFromWire(max_cash_spent)

    availableToWithdraw: (ticker) =>
        margin = @calculateMargin()
        high_margin = margin[1]
        if ticker is "BTC"
            return @positions[ticker].position - high_margin


    calculateMargin: (new_order) =>
        low_margin = 0
        high_margin = 0
        #TODO: add futures here

        orders = (order for id, order of @orders)
        if new_order?
            orders.push new_order

        sum = (t, s) -> t + s

        for ticker, position of @positions
            contract = @markets[ticker]
            buy_quantities = (order.quantity_left for order in orders when order.contract == ticker and order.side == 'BUY')
            max_position = position.position + buy_quantities.reduce sum, 0

            sell_quantities = (order.quantity_left for order in orders when order.contract == ticker and order.side == 'SELL')
            min_position = position.position - sell_quantities.reduce sum, 0

            if contract.contract_type is "futures"
                # NOT IMPLEMENTED
                @error "Futures not implemented"
            else if contract.contract_type == "prediction"
                payoff = contract.lot_size
                spending = (order.quantity_left * order.price * @markets[order.contract].lot_size / @markets[order.contract].denominator for order in orders when order.contract == ticker and order.side == "BUY")
                receiving = (order.quantity_left * order.price * @markets[order.contract].lot_size / @markets[order.contract].denominator for order in orders when order.contract == ticker and order.side == "SELL")
                max_spent = spending.reduce sum, 0
                max_received = receiving.reduce sum, 0
                if min_position < 0
                    worst_short_cover = -min_position * payoff
                else
                    worst_short_cover = 0

                if max_position < 0
                    best_short_cover = -max_position * payoff
                else
                    best_short_cover = 0

                additional_margin = Math.max(max_spent + best_short_cover, -max_received + worst_short_cover)
                low_margin += additional_margin
                high_margin += additional_margin


        max_cash_spent = {}
        for ticker of @markets
            # "defaultdict"
            if @markets[ticker].contract_type is "cash"
                max_cash_spent[ticker] = 0

        # Deal with cash orders seperately because there are no cash_pair positions
        for order in orders
            if @markets[order.contract].contract_type is "cash_pair"
                from_contract = @markets[order.contract].denominated_contract_ticker
                payout_contract = @markets[order.contract].payout_contract_ticker
                switch order.side
                    when "BUY"
                        transaction_size = order.quantity_left * order.price / (@markets[order.contract].denominator * @markets[payout_contract].denominator)
                        max_cash_spent[from_contract] += transaction_size
                    when "SELL"
                        max_cash_spent[payout_contract] += order.quantity_left

        for cash_ticker, max_spent of max_cash_spent
            if cash_ticker is "BTC"
                additional_margin = max_spent
            else
                position = @positions[cash_ticker]?.position or 0
                additional_margin = if max_spent <= position then 0 else Math.pow(2, 48)

            low_margin += additional_margin
            high_margin += additional_margin

        @log ["Margin:", low_margin, high_margin]
        @log ["cash_spent", max_cash_spent]
        return [low_margin, high_margin, max_cash_spent]


if module?
    module.exports =
        Sputnik: @Sputnik

