ab = require "./autobahn.node.js"
EventEmitter = require("./events").EventEmitter

### UI API ###

class Sputnik extends EventEmitter

    markets: {}

    orders: {}
    positions: {}
    margins: {}
    authenticated: false
    profile:
        email: null
        nickname: null
    chat_messages: []

    constructor: (@uri) ->


        ### Sputnik API  ###

        # network control

    connect: () =>
        ab.connect @uri, @onOpen, @onClose

    close: () =>
        @session?.close()
        @session = null

    # market selection

    follow: (market) =>
        @subscribe "book##{market}", @onBook
        @subscribe "trades##{market}", @onTrade
        @subscribe "safe_prices##{market}", @onSafePrice

    unfollow: (market) =>
        @unsubscribe "book##{market}"
        @unsubscribe "trades##{market}"
        @unsubscribe "safe_prices##{market}"

    # authentication and account management

    makeAccount: (username, secret, email) =>
        @log "Computing password hash..."
        salt = Math.random().toString(36).slice(2)
        @authextra =
            salt: salt
            iterations: 1000
        password = ab.deriveKey secret, @authextra

        @call("make_account", username, password, salt, email).then \
            (result) =>
                @emit "make_account_success", result
            , (error) =>
                @emit "make_account_fail", error

    getProfile: () =>
        @call("get_profile").then (@profile) =>
            @emit "profile", @profile

    changeProfile: (nickname, email) =>
        @call("change_profile", email, nickname).then (@profile) =>
            @emit "profile", @profile

    authenticate: (login, password) =>
        if not @session?
            @wtf "Not connected."

        @session.authreq(login).then \
            (challenge) =>
                @authextra = JSON.parse(challenge).authextra
                secret = ab.deriveKey(password, @authextra)
                signature = @session.authsign(challenge, secret)
                @session.auth(signature).then @onAuthSuccess, @onAuthFail
            , (error) =>
                @wtf "Failed login: Could not authenticate: #{error}."

    changePassword: (old_password, new_password) =>
        if not @authenticated
            @wtf "Not logged in."

        old_secret = ab.deriveKey(old_password, @authextra)
        new_secret = ab.deriveKey(new_password, @authextra)
        @call("change_password", old_secret, new_secret).then \
            (message) =>
                @log "password changed successfully"
                @emit "change_password_success", message
            , (error) =>
                @error "password change error: #{error}"
                @emit "change_password_fail", error

    restoreSession: (uid) =>
        if not @session?
            @wtf "Not connected."

        @session.authreq(uid).then \
            (challenge) =>
                # TODO: Why is this secret hardcoded?
                secret = "EOcGpbPeYMMpL5hQH/fI5lb4Pn2vePsOddtY5xM+Zxs="
                signature = @session.authsign(challenge, secret)
                @session.auth(signature).then @onAuthSuccess, @onSessionExpired
            , (error) =>
                @wtf "RPC Error: Could not authenticate: #{error}."

    logout: () =>
        @authenticated = false
        @call "logout"
        @close()
        @emit "logout"
        # Reconnect after logout
        @connect()

    getCookie: () =>
        @call("get_cookie").then \
            (uid) =>
                @log("cookie: " + uid)
                @emit "cookie", uid

    onAuthSuccess: (permissions) =>
        @log("authenticated!", JSON.stringify(permissions))
        @authenticated = true

        @getProfile()
        @getSafePrices()
        @getOpenOrders()
        @getPositions()

        @username = permissions.username
        @emit "auth_success", @username

        try
            @subscribe "orders#" + @username, @onOrder
            @subscribe "fills#" + @username, @onFill
            @subscribe "fees#" + @username, @onFee
        catch error
            @log error

    onAuthFail: (error) =>
        @username = null
        [code, reason] = error
        @emit "auth_fail", error

    onSessionExpired: (error) =>
        @emit "session_expired"

    # data conversion

    cstFromTicker: (ticker) =>
        contract = @markets[ticker]
        if contract.contract_type is "cash_pair"
            [t, s] = ticker.split("/")
            source = @markets[s]
            target = @markets[t]
        else
            source = @markets["BTC"]
            target = @markets[ticker]
        return [contract, source, target]

    timeFormat: (timestamp) =>
        dt = new Date(timestamp / 1000)
        return dt.toLocaleTimeString()

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
        return ohlcv

    positionFromWire: (wire_position) =>
        ticker = wire_position.contract
        position = @copy(wire_position)
        position.position = @quantityFromWire(ticker, wire_position.position)
        position.reference_price = @priceFromWire(ticker, wire_position.reference_price)
        return position

    orderToWire: (order) =>
        ticker = order.contract
        wire_order = @copy(order)
        wire_order.price = @priceToWire(ticker, order.price)
        wire_order.quantity = @quantityToWire(ticker, order.quantity)
        wire_order.quantity_left = @quantityToWire(ticker, order.quantity_left)
        return wire_order

    orderFromWire: (wire_order) =>
        ticker = wire_order.contract
        order = @copy(wire_order)
        order.price = @priceFromWire(ticker, wire_order.price)
        order.quantity = @quantityFromWire(ticker, wire_order.quantity)
        order.quantity_left = @quantityFromWire(ticker, wire_order.quantity_left)
        order.timestamp = @timeFormat(wire_order.timestamp)
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
        trade.wire_timestamp = wire_trade.timestamp
        trade.timestamp = @timeFormat(wire_trade.timestamp)
        return trade

    quantityToWire: (ticker, quantity) =>
        [contract, source, target] = @cstFromTicker(ticker)
        quantity = quantity * target.denominator
        quantity = quantity - quantity % contract.lot_size
        return quantity

    priceToWire: (ticker, price) =>
        [contract, source, target] = @cstFromTicker(ticker)
        price = price * source.denominator * contract.denominator
        price = price - price % contract.tick_size
        return price

    quantityFromWire: (ticker, quantity) =>
        [contract, source, target] = @cstFromTicker(ticker)

        return quantity / target.denominator

    priceFromWire: (ticker, price) =>
        [contract, source, target] = @cstFromTicker(ticker)

        return price / (source.denominator * contract.denominator)

    getPricePrecision: (ticker) =>
        [contract, source, target] = @cstFromTicker(ticker)

        return Math.log(source.denominator / contract.tick_size) / Math.LN10

    getQuantityPrecision: (ticker) =>
        [contract, source, target] = @cstFromTicker(ticker)

        # TODO: account for contract denominator
        return Math.log(target.denominator / contract.lot_size) / Math.LN10

    # order manipulation
    placeOrder: (quantity, price, ticker, side) =>
        order =
            quantity: quantity
            price: price
            contract: ticker
            side: side
        @log "placing order: #{order}"
        @call("place_order", @orderToWire(order)).then \
            (res) =>
                @emit "place_order_success", res
            , (error) =>
                @emit "place_order_fail", error

    cancelOrder: (id) =>
        @log "cancelling: #{id}"
        @call("cancel_order", id).then \
            (res) =>
                @emit "cancel_order_success", res
            , (error) =>
                @emit "cancel_order_fail", error

    # deposits and withdrawals

    makeCompropagoDeposit: (store, amount, send_sms) =>
        charge =
          product_price: amount
          payment_type: store
          send_sms: send_sms
          currency: "MXN"
        @log "compropago charge: #{charge}"
        @call("make_compropago_deposit", charge).then \
            (@ticket) =>
                @log "compropago deposit ticket: #{ticket}"
                @emit "compropago_deposit_success", ticket
            , (error) =>
                @error "compropago error: #{error}"
                @emit "compropago_deposit_fail", error

    getAddress: (contract) =>
        @call("get_current_address", contract).then \
            (address) =>
                @log "address for #{contract}: #{address}"
                @emit "address", [contract, address]

    newAddress: (contract) =>
        @call("get_new_address", contract).then \
            (address) =>
                @log "new address for #{contract}: #{address}"
                @emit "address", [contract, address]
        , (error) =>
            @log "new address failure for #{contract}: #{error}"
            @emit "new_address_fail", error

    withdraw: (contract, address, amount) =>

    # account/position information
    getSafePrices: () =>
    getOpenOrders: () =>
        @call("get_open_orders").then \
            (@orders) =>
                @log("orders received: #{orders}")
                orders = {}
                for id, order of @orders
                    if order.quantity_left > 0
                        orders[id] = @orderFromWire(order)

                @emit "orders", orders

    getPositions: () =>
        @call("get_positions").then \
            (@positions) =>
                @log("positions received: #{@positions}")
                positions = {}
                for ticker, position of @positions
                    positions[ticker] = @positionFromWire(position)

                @emit "positions", positions

    getOrderBook: (ticker) =>
        @call("get_order_book", ticker).then @onBook

    getTradeHistory: (ticker) =>
        @call("get_trade_history", ticker).then @onTradeHistory

    getOHLCV: (ticker) =>
        @call("get_ohlcv", ticker).then @onOHLCV

    # miscelaneous methods

    chat: (message) =>
        if @authenticated
            @publish "chat", message
            return [true, null]
        else
            return [false, "Not logged in"]

    ### internal methods ###

    # RPC wrapper
    call: (method, params...) =>
        if not @session?
            return @wtf "Not connected."
        @log "Invoking RPC #{method}(#{params})"
        d = ab.Deferred()
        @session.call("#{@uri}/rpc/#{method}", params...).then \
            (result) =>
                if result.length != 2
                    @warn "RPC Warning: sputnik protocol violation in #{method}"
                    return d.resolve result
                if result[0]
                    return d.resolve result[1]
                else
                    @warn "RPC call failed: #{result[1]}"
                    return d.reject result[1]
            , (error) =>
                @wtf "RPC Error: #{error.desc} in #{method}"


    subscribe: (topic, callback) =>
        if not @session?
            return @wtf "Not connected."
        @session.subscribe "#{@uri}/feeds/#{topic}", (topic, event) ->
            callback event

    unsubscribe: (topic) =>
        if not @session?
            return @wtf "Not connected."
        @session.unsubscribe "#{@uri}/feeds/#{topic}"

    publish: (topic, message) =>
        if not @session?
            return @wtf "Not connected."
        @log "Publishing #{message} on #{topic}"
        @session.publish "#{@uri}/feeds/#{topic}", message, false

    # logging
    log: (obj) =>
        console.log obj
        @emit "log", obj
    warn: (obj) ->
        console.warn obj
        @emit "warn", obj
    error: (obj) ->
        console.error obj
        @emit "error", obj
    wtf: (obj) => # What a Terrible Failure
        @error obj
        @emit "wtf", obj

    # connection events
    onOpen: (@session) =>
        @log "Connected to #{@uri}."

        @call("get_markets").then @onMarkets, @wtf
        @subscribe "chat", @onChat
        # TODO: Are chats private? Do we want them for authenticated users only?
        @call("get_chat_history").then \
            (chats) =>
                for chat in chats
                    user = chat[0]
                    msg = chat[1]
                    @chat_messages.push "#{user}: #{msg}"
                @emit "chat", @chat_messages

        @emit "open"

    onClose: (code, reason, details) =>
        @log "Connection lost."
        @emit "close"

    # authentication internals

    # default RPC callbacks

    onMarkets: (@markets) =>
        for ticker of markets
            @markets[ticker].trades = []
            @markets[ticker].bids = []
            @markets[ticker].asks = []
        @emit "markets", @markets

    # feeds
    onBook: (book) =>
        @log "book received: #{book}"

        @markets[book.contract].bids = book.bids
        @markets[book.contract].asks = book.asks

        books = {}
        for contract, market of @markets
            if market.contract_type != "cash"
                books[contract] =
                    contract: contract
                    bids: @bookRowFromWire(contract, order) for order in market.bids
                    asks: @bookRowFromWire(contract, order) for order in market.asks

        @emit "book", books

    # Make sure we only have the last hour of trades
    cleanTradeHistory: (ticker) =>
        now = new Date()
        an_hour_ago = new Date()
        an_hour_ago.setHours(now.getHours() - 1)
        while @markets[ticker].trades[0].timestamp / 1000 < an_hour_ago.getTime()
            @markets[ticker].trades.shift()

    emitTradeHistory: (ticker) =>
        trade_history = {}
        trade_history[ticker] = for trade in @markets[ticker].trades
            @tradeFromWire(trade)

        @emit "trade_history", trade_history

    onTradeHistory: (trade_history) =>
        @log "trade_history received: #{trade_history}"
        if trade_history.length > 0
            ticker = trade_history[0].contract
            @markets[ticker].trades = trade_history
            @cleanTradeHistory(ticker)
            @emitTradeHistory(ticker)
        else
            @warn "no trades in history"

    onOHLCV: (wire_ohlcv) =>
        @log "ohlcv received: #{ohlcv}"
        ohlcv = {}
        for timestamp, entry of wire_ohlcv
            ohlcv[timestamp] = @ohlcvFromWire(entry)
        @emit "ohlcv", ohlcv

    onTrade: (trade) =>
        ticker = trade.contract
        @markets[ticker].trades.push trade
        @emit "trade", @tradeFromWire(trade)
        @cleanTradeHistory(ticker)
        @emitTradeHistory(ticker)

    onChat: (event) =>
        # TODO: Something is wrong where my own chats don't show up in this box-- but they do get sent
        user = event[0]
        message = event[1]
        @chat_messages.push "#{user}: #{message}"
        @log "Chat: #{user}: #{message}"
        @emit "chat", @chat_messages

    # My orders get updated with orders
    onOrder: (order) =>
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

    onFee: (fee) =>
        @log "fee received: #{fee}"
        @emit "fee", @positionFromWire(fee)
        @positions[fee.contract].position -= fee.position
        @emitPositions

    # My positions and available margin get updated with fills
    onFill: (fill) =>
        @log "fill received: #{fill}"
        @emit "fill", @tradeFromWire(fill)
        [contract, source, target] = @cstFromTicker(fill.contract)
        if contract.contract_type == "cash_pair"
            if fill.side == "SELL"
                sign = -1
            else
                sign = 1
            @positions[source.ticker].position -= fill.quantity * fill.price * sign / target.denominator
            @positions[target.ticker].position += fill.quantity * sign
        else
            @error "only cash_pair contracts implemented in onFill"

        @emitPositions

    emitPositions: () =>
        positions = {}
        for ticker, position of @positions
            positions[ticker] = @positionFromWire(position)

        @emit "positions", positions

module.exports =
    Sputnik: Sputnik

