updateTable = (id, data) ->
    rows = ("<tr><td>#{price}</td><td>#{quantity}</td></tr>" for [price, quantity] in data)
    $("##{id}").html rows.join("")

initPlot = () ->
    d1 = ([i/2, 30*Math.sin(i/2) + 55] for i in [0..28])
    d2 = ([i, 100*Math.sin(i) + 100] for i in [0..13])
    $.plot "#graph",
        [{data:d1, yaxis:1}, {data:d2, bars:{show:true}, yaxis:2}],
        {yaxes:[{position:"left"}, {position:"right"}]}

updateBuys = (data) ->
    data.sort (a, b) -> b[0] - a[0]
    updateTable "buys", data
    best_offer = Math.max 0, (price for [price, quantity] in data)...
    $("#sell_price").attr "placeholder", best_offer

updateSells = (data) ->
    data.sort (a, b) -> a[0] - b[0]
    updateTable "sells", data
    best_offer = Math.min (price for [price, quantity] in data)...
    $("#buy_price").attr "placeholder", best_offer

updateTrades = (data) ->
    updateTable "trades", data

$ ->
    initPlot()
    sample_buys = [[1, 2], [2, 3]]
    sample_sells = [[3, 1], [4, 2]]
    sample_trades = [[2.5, 100]]
    updateBuys sample_buys
    updateSells sample_sells
    updateTrades sample_trades

$("#login").click () ->
    $("#register").toggle()
    $("#ftc_balance").toggle()
    $("#ltc_balance").toggle()
    $("#buy_panel").toggle()
    $("#sell_panel").toggle()
    $("#orders_panel").toggle()
    if $("#login").text() is "Log in"
        $("#login").text "Log out"
    else
        $("#login").text "Log in"

