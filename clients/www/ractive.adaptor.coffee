class RactiveSputnikWrapper
    constructor: (@ractive, @sputnik, @keypath, @prefix) ->
        @markets = {}
        @types = {}

        @sputnik.on "markets", (markets) =>
            @markets = {}
            @types = {}
            for ticker, market of markets
                if market.contract_type isnt "cash"
                    @markets[ticker] = market
                    @markets[ticker].best_ask = {price: Infinity, quantity: 0}
                    @markets[ticker].best_bid = {price: 0, quantity: 0}
                    type = market.contract_type
                    (@types[type] or (@types[type] = [])).push ticker
            @notify "markets"
            @notify "types"

        @sputnik.on "book", (book) =>
            ticker = book.contract

            @markets[ticker].bids = book.bids
            @markets[ticker].asks = book.asks

            @markets[ticker].best_ask = {price: Infinity, quantity: 0}
            @markets[ticker].best_bid = {price: 0, quantity: 0}
            if book.asks.length
                @markets[ticker].best_ask = book.asks[0]
            if book.bids.length
                @markets[ticker].best_bid = book.bids[0]

            @notify "markets"

    notify: (property) =>
        @setting = true
        @ractive.set @prefix property
        @setting = false

    get: () ->
        markets: @markets
        types: @types

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

