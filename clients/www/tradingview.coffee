if module?
    global.window = require "./window.js"
    global.ab = global.window.ab
    global.EventEmitter = require("./events").EventEmitter

### TradingView API ###

class @TVFeed
    subscribed: {}
    quotes: {}

    constructor: (@sputnik) ->
        # Trading View API

    setup: (reserved, callback) =>
        config_data = {
            exchanges: [ 'sputnik' ]
            symbolsTypes: [ 'cash_pair', 'futures', 'prediction' ]
            supportedResolutions: [1, 60, 'D']
            supports_marks: false
        }

    searchSymbolsByName: (userInput, exchange, symbolType, onResultReadyCallback) =>
        return_array = []
        for ticker, details of @sputnik.markets
            if details.contract_type is symbolType and ticker.indexOf(userInput) > -1
                return_array.append {
                        symbol: ticker,
                        full_name: details.description,
                        exchange: 'sputnik',
                        ticker: ticker,
                        type: details.contract_type
                }

        onResultReadyCallback(return_array)

    resolveSymbol: (symbolName, onSymbolResolvedCallback, onResolveErrorCallback) =>
        if symbolName in @sputnik.markets
            info = {
                name: symbolName
                "exchange-traded": 'sputnik'
                "exchange-listed": 'sputnik'
                timezone: 'Europe/London',
                pricescale: @sputnik.getPriceScale(symbolName)
                minmove: @sputnik.getMinMove(symbolName)
                has_intraday: true
                intraday_multipliers: [1]
                has_daily: true
                has_weekly_and_monthly: false
                has_empty_bars: true
                force_session_rebuild: false
                has_no_volume: false
                #volume_precision: @sputnik.getQuantityPrecision(symbolName)
                has_fractional_volume: true
                ticker: symbolName
                description: @sputnik.markets[symbolName].description
                session: "24x7"
                data_status: 'REALTIME'
                supported_resolutions: [1, 60, 'D']
                type: @sputnik.markets[symbolName].contract_type
            }
            onSymbolResolvedCallback info


    getBars: (symbolInfo, resolution, from, to, onHistoryCallback, onErrorCallBack) =>
        from_timestamp = from * 1e6
        to_timestamp = to * 1e6
        if resolution is 1
            period = "minute"
        else if resolution is 60
            period = "hour"
        else if resolution is "D"
            period = "day"

        @sputnik.call("get_ohlcv_history", symbolInfo.name, period, from_timestamp, to_timestamp).then (history) =>
            return_bars = []
            for timestamp, bar of history
                return_bars.append {
                    time: imestamp / 1e3
                    open: @sputnik.priceFromWire(symbolInfo.name, bar.open)
                    close: @sputnik.priceFromWire(symbolInfo.name, bar.close)
                    high: @sputnik.priceFromWire(symbolInfo.name, bar.high)
                    low: @sputnik.priceFromWire(symbolInfo.name, bar.low)
                    volume: @sputnik.quantityFromWire(symbolInfo.name, bar.volume)
                }
            onHistoryCallback(return_bars)
        , (error) =>
            onErrorCallBack(error)

    subscribeBars: (symbolInfo, reoslution, onRealtimeCallback, subscriberUID) =>
        if resolution is 1
            period = "minute"
        else if resolution is 60
            period = "hour"
        else if resolution is "D"
            period = "day"

        @sputnik.subscribe "ohlcv##{symbolInfo.name}", (bar) =>
            if bar.period is period
                return_bar = {
                    time: ohlcv.timestamp / 1e3
                    open: @sputnik.priceFromWire(symbolInfo.name, bar.open)
                    close: @sputnik.priceFromWire(symbolInfo.name, bar.close)
                    high: @sputnik.priceFromWire(symbolInfo.name, bar.high)
                    low: @sputnik.priceFromWire(symbolInfo.name, bar.low)
                    volume: @sputnik.quantityFromWire(symbolInfo.name, bar.volume)
                }
                onRealtimeCallback(return_bar)
        if subscriberUID in @subscribed
            @subscribed[subscriberUID].append symbolInfo.name
        else
            @subscribed[subscriberUID] = [symbolInfo.name]

    unsubscribeBars: (subscriberUID) =>
        if subscriberUID in @subscribed
            for symbol in @subscribed[subscriberUID]
                @sputnik.unsubscribe "ohlcv##{@subscribed[subscriberUID]}"
                delete @subscribed[subscriberUID]

    getQuotes: (symbols, onDataCallback, onErrorCallback) =>
        dlist = []
        for symbol in symbols
            dlist.append @call("get_order_book", symbol)

        $.when(dlist).then (results) =>
            onDataCallback(results)

    subscribeQuotes: (symbols, fastSymbols, onRealtimeCallback, subscriberUID) =>
        for symbol in symbols + fastSymbols
            @sputnik.subscribe("book##{symbol}").then (book) =>
                onRealtimeCallback(book)

        if subscriberUID in @quotes
            @quotes[subscriberUID].push.apply @quotes[subscriberUID], symbols + fastSymbols
        else
            @quotes[subscriberUID] = symbols + fastSymbols

    unsubscribeQuotes: (subscriberUID) =>
        for symbol in @quotes[subscriberUID]
            @sputnik.unsubscribe("book##{symbol}")

        delete @quotes[subscriberUID]














