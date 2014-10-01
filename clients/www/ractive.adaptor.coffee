class RactiveSputnikWrapper
    constructor: (@ractive, @sputnik, @keypath, @prefix) ->
        @logged_in = false
        @username = null
        @markets = {}
        @types = {}
        @books = {}
        @positions = {}
        @margin = [0, 0]
        @trade_history = {}
        @orders = []
        @ohlcv = {}

        @sputnik.on "auth_success", (username) =>
            @logged_in = true
            @username = username
            console.log "logged in as #{username}"

            @notify "logged_in"

        @sputnik.on "markets", (markets) =>
            @sputnik.log ["markets", markets]
            @markets = {}
            @types = {}

            for ticker, market of markets
                if market.contract_type isnt "cash"
                    @markets[ticker] = market
                    type = market.contract_type
                    (@types[type] or (@types[type] = [])).push ticker

            @notify "markets"
            @notify "types"

        @sputnik.on "book", (book) =>
            @sputnik.log ["book", book]
            ticker = book.contract

            @books[ticker] =
                bids: book.bids
                asks: book.asks
                best_ask:
                    price: Infinity
                    quantity: 0
                best_bid:
                    price: 0
                    quantity: 0

            for entry in @books[ticker].bids
                entry.price = entry.price.toFixed(@sputnik.getPricePrecision(ticker))
                entry.quantity = entry.quantity.toFixed(@sputnik.getQuantityPrecision(ticker))

            for entry in @books[ticker].asks
                entry.price = entry.price.toFixed(@sputnik.getPricePrecision(ticker))
                entry.quantity = entry.quantity.toFixed(@sputnik.getQuantityPrecision(ticker))

            if book.asks.length
                @books[ticker].best_ask = book.asks[0]
            if book.bids.length
                @books[ticker].best_bid = book.bids[0]

            @notify "books"

        @sputnik.on "trade_history", (trade_history) =>
            @sputnik.log ["trade_history", trade_history]
            for ticker, history of trade_history
                @trade_history[ticker] = history.reverse()
                for trade in @trade_history[ticker]
                    trade.price = trade.price.toFixed(@sputnik.getPricePrecision(ticker))
                    trade.quantity = trade.quantity.toFixed(@sputnik.getQuantityPrecision(ticker))

            @notify "trade_history"

        sputnik.on "positions", (positions) =>
            @sputnik.log ["positions", positions]
            for ticker, position of positions
                if @markets[ticker]?.contract_type isnt "cash_pair"
                    @positions[ticker] = position
                    @positions[ticker].position_fmt = position.position.toFixed(@sputnik.getQuantityPrecision(ticker))

            @sputnik.log ["positions2", @positions]
            @notify "positions"
        
        sputnik.on "margin", (margin) =>
            @sputnik.log ["margin", margin]
            @margin = margin

            @notify "margin"

        sputnik.on "orders", (orders) =>
            @sputnik.log ["orders", orders]
            @orders = orders
            for id, order of @orders
                order.price = order.price.toFixed(@sputnik.getPricePrecision(order.contract))
                order.quantity = order.quantity.toFixed(@sputnik.getQuantityPrecision(order.contract))
                order.quantity_left = order.quantity_left.toFixed(@sputnik.getQuantityPrecision(order.contract))

            @notify "orders"

        sputnik.on "ohlcv_history", (ohlcv_history) =>
            @sputnik.log ["ohlcv_history", ohlcv_history]
            keys = Object.keys(ohlcv_history)
            if keys.length
                last_key = keys[keys.length-1]
                ohlcv = ohlcv_history[last_key]
                update_ohlcv(ohlcv)

        update_ohlcv = (ohlcv) =>
            ohlcv.close = ohlcv.close.toFixed(@sputnik.getPricePrecision(ohlcv.contract))
            ohlcv.high = ohlcv.high.toFixed(@sputnik.getPricePrecision(ohlcv.contract))
            ohlcv.low = ohlcv.low.toFixed(@sputnik.getPricePrecision(ohlcv.contract))
            ohlcv.open = ohlcv.open.toFixed(@sputnik.getPricePrecision(ohlcv.contract))
            ohlcv.vwap = ohlcv.vwap.toFixed(@sputnik.getPricePrecision(ohlcv.contract))
            ohlcv.volume = ohlcv.volume.toFixed(@sputnik.getQuantityPrecision(ohlcv.contract))

            if ohlcv.contract of @ohlcv
                @ohlcv[ohlcv.contract][ohlcv.period] = ohlcv
            else
                @ohlcv[ohlcv.contract] = {}
                @ohlcv[ohlcv.contract][ohlcv.period] = ohlcv

            @notify "ohlcv"

        sputnik.on "ohlcv", (ohlcv) =>
            @sputnik.log ["ohlcv", ohlcv]
            update_ohlcv(ohlcv)

    notify: (property) =>
        @setting = true
        @ractive.set @prefix property
        @setting = false

    get: () ->
        logged_in: @logged_in
        username: @username
        markets: @markets
        types: @types
        books: @books
        positions: @positions
        margin: @margin
        trade_history: @trade_history
        orders: @orders
        ohlcv: @ohlcv

    set: (property, value) =>
        # this is called both, when we update, and when the user updates
        # we do not want infinite loops, so check
        # check for internal event

        if @setting
            return

    reset: (data) =>
        return false

    teardown: () =>
        delete @sputnik

Ractive.adaptors.Sputnik =
    filter: (object) ->
        object instanceof Sputnik

    wrap: (ractive, sputnik, keypath, prefix) ->
        new RactiveSputnikWrapper(ractive, sputnik, keypath, prefix)

