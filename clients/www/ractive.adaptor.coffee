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

        @sputnik.on "auth_success", (username) =>
            @logged_in = true
            @username = username
            console.log "logged in as #{username}"

            @notify "logged_in"

        @sputnik.on "markets", (markets) =>
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
            for ticker, history of trade_history
                @trade_history[ticker] = history.reverse()
                for trade in @trade_history[ticker]
                    trade.price = trade.price.toFixed(@sputnik.getPricePrecision(ticker))
                    trade.quantity = trade.quantity.toFixed(@sputnik.getQuantityPrecision(ticker))

            @notify "trade_history"

        sputnik.on "positions", (positions) =>
            for ticker, position of positions
                if @markets[ticker]?.contract_type isnt "cash_pair"
                    @positions[ticker] = position
            
            @notify "positions"
        
        sputnik.on "margin", (margin) =>
            @margin = margin
            
            @notify "margin"

        sputnik.on "orders", (orders) =>
            @orders = orders
            for id, order of @orders
                order.price = order.price.toFixed(@sputnik.getPricePrecision(order.contract))
                order.quantity = order.quantity.toFixed(@sputnik.getQuantityPrecision(order.contract))
                order.quantity_left = order.quantity_left.toFixed(@sputnik.getQuantityPrecision(order.contract))

            @notify "orders"

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

