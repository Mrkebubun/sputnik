class RactiveSputnikWrapper
    constructor: (@ractive, @sputnik, @keypath, @prefix) ->
        @markets = {}
        @ticker = null
        @sputnik.on "markets", (markets) =>
            for ticker, market of markets
                if market.contract_type is "cash_pair"
                    @markets[ticker] = market
            @notify "markets"
            @ractive.set @prefix "ticker", Object.keys(@markets)[0]
        @sputnik.on "book", (book) =>
            ticker = book.contract
            @markets[ticker].bids = book.bids
            @markets[ticker].asks = book.asks
            @notify "markets"

    notify: (property) =>
        @setting = true
        @ractive.set @prefix property
        @setting = false

    get: () ->
        markets: @markets
        ticker: @ticker

    set: (property, value) =>
        # this is called both, when we update, and when the user updates
        # we do not want infinite loops, so check
        # check for internal event

        if @setting
            return

        if property == "ticker"
            if @ticker?
                @sputnik.unfollow @ticker
            @ticker = value
            if @ticker?
                @sputnik.follow @ticker
                @sputnik.getOrderBook @ticker

    reset: (data) =>
        return false

    teardown: () =>
        delete @sputnik

Ractive.adaptors.Sputnik =
    filter: (object) ->
        object instanceof Sputnik

    wrap: (ractive, sputnik, keypath, prefix) ->
        new RactiveSputnikWrapper(ractive, sputnik, keypath, prefix)

