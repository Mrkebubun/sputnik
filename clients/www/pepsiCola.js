/*var host = "cbnypao55fhrj24k.onion";*/
var session = null;
var logged_in = false;

var QBUY, QSELL, PBUY, PSELL;
var MARKETS;
var SITE_TICKER = 'ERROR';
var TRADE_HISTORY = [];
var MAX_CHAT_LINES = 100;
var SITE_POSITIONS = [];
var OPEN_ORDERS = [];
var ORDER_BOOK; //Global variable will be useful when depth graph is built.

var ORDER_BOOK_VIEW_SIZE = false;

var CHAT_MESSAGES = [];
var SAFE_PRICES = Object();

var base_uri = "http://example.com/";

var myTopic = base_uri + "topics/mytopic1";

var chat_URI = base_uri + "user/chat";
var fills_URI = base_uri + "user/fills#";
var cancels_URI = base_uri + "user/cancels#";
var open_orders_URI = base_uri + "user/open_orders#";
var trade_URI = base_uri + "trades#";
var safe_prices_URI = base_uri + "safe_prices#";
var order_book_URI = base_uri + "order_book#";


window.onload = function () {
    connect();
};

function onChat(channelURI, msg) {
    // console.log("Received chat message in channel " + channelURI + ":" + msg);
    var user = msg[0];
    var message = msg[1];
    CHAT_MESSAGES.push('&lt;' + user + '&gt; ' + message)
    if (CHAT_MESSAGES.length > MAX_CHAT_LINES)
        CHAT_MESSAGES.shift();


    $('#chatArea').html(CHAT_MESSAGES.join('\n'));
    //for(var i = 0; i < CHAT_MESSAGES.length; ++i)
    //    $('#chatArea').append(CHAT_MESSAGES[i]+'\n');

    $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight);
}

function onSafePrice(uri, event) {
    var ticker = uri.split('#')[1];
    SAFE_PRICES[ticker] = event;
    console.log(SAFE_PRICES)
}

function onConnect() {
    console.log("Connected!")
    getMarkets();
    getChatHistory();
    session.subscribe(chat_URI, onChat);

    var scalingFactor = $(window).height()/$(window).width();
    $('.centertop').css('width',parseInt(100*scalingFactor*0.55) + '%');
    //session.subscribe("http://example.com/simple", onEvent);
    /*for testing:*/
    //do_login('a', 'a');
    //console.log('subscribed')
}

function onAuth(permissions) {
    ab.log("authenticated!", JSON.stringify(permissions));
    console.log('permissions (want the uris):',permissions);
    //session.subscribe(myTopic, onEvent);
    logged_in = true;


    $('#logoutButton').show();
    $('#loginStatus').show();
    $('#loginStatus').text('logged in as ' + login.value);

    $('#loginButton').hide();
    $('#registration').hide();

    // Initialize for user.  Maybe move the call for markets to before auth?
    //make this chain correctly...or better yet, make it publish upon connection
    //via serverside

    //getSafePrices(Object.keys(MARKETS));
    getSafePrices();
    getOpenOrders();
    getPositions();

    /*
    the gleaning of the user_id from the permissions and then manual 
    subscription process is very hacky.  Hope to make it more clean later.
    */
    var user_id;
    user_id = _.pluck(permissions.pubsub, 'uri')[1].split('#')[1]
    console.log(cancels_URI + user_id );

    try{session.subscribe(cancels_URI + user_id, onCancel);}
        catch(err){console.log(err);}
    try{session.subscribe(fills_URI + user_id, onFill);}
        catch(err){console.log(err);}
    try{ session.subscribe(open_orders_URI + user_id, onOpenOrder);}
        catch(err){console.log(err);}

    //possible to subscribe to chat, but not pub before auth?
    session.subscribe(chat_URI, onChat);

    // obviously need to un hardcode this...
    //	subToTradeStream(16);
    //	subToTradeStream(17);
    //	subToSafePrice('USD.13.7.31');
    //	subToOrderBook('USD.13.7.31');
    //	subToFills(8);
    //	subToCancels(8);
    //    subToOpenOrders(8);

    //no longer necessary to switch to trade immediatealy as we have asplash screen.
    //switchToTrade ('USD.13.7.31')


}

function onEvent(topicUri, event) {
    console.log('in onEvent', SITE_TICKER, topicUri, event);

    if (SITE_TICKER in JSON.parse(event)) {
        console.log('got event');
        //todo: find where needed
        orderBook(SITE_TICKER);
        //getTradeHistory(SITE_TICKER);
    }
}

function onBookUpdate(topicUri, event) {
    console.log('in onBookUpdate');
    //console.log('in onBookUpdate', SITE_TICKER, topicUri, event);
	ORDER_BOOK = JSON.parse(event);
	updateOrderBook(ORDER_BOOK,ORDER_BOOK_VIEW_SIZE);
}

function onFill(topicUri, event) {
    //must get rid of safe price rpc!
    getSafePrices(Object.keys(MARKETS));


    console.log('in onFill', SITE_TICKER, topicUri, event);
    OPEN_ORDERS = _.reject(OPEN_ORDERS, function (ord) {return ord['order_id']== event['order'];});
    //sendChat('filled order: '+JSON.stringify(event) );
    displayPositions(false,SITE_POSITIONS);
    displayPositions(true,SITE_POSITIONS);
    displayOrders(false,OPEN_ORDERS);
    displayOrders(true,OPEN_ORDERS);
    //reload position tableS
    //make some sort of notification to user
}

function onOpenOrder(topicUri, event) {
    //must get rid of safe price rpc!
    getSafePrices(Object.keys(MARKETS));

    console.log('in onOpenOrder', SITE_TICKER, topicUri, event);

    var new_open_order = {'order_id': event['order'],
                          'price':    event['price'],
                          'quantity': event['quantity'],
                          'side':     event['side']==0?'BUY':'SELL',
                          'ticker':   event['ticker']};
    console.log(new_open_order);
    OPEN_ORDERS.push(new_open_order);
    
    // publish to seperate feed, not chat.
    //sendChat('placed order: '+JSON.stringify(event) );

//    displayPositions(false,SITE_POSITIONS);
//    displayPositions(true,SITE_POSITIONS);
//      replace with 
    getPositions();
    displayOrders(false,OPEN_ORDERS);
    displayOrders(true,OPEN_ORDERS);
}

function onCancel(topicUri, event) {
    console.log('in onCancel', SITE_TICKER, topicUri, event);

    console.log(event);
    console.log('before', OPEN_ORDERS)
    OPEN_ORDERS = _.reject(OPEN_ORDERS, function (ord) {return ord['order_id']== event['order'];});
    console.log('after', OPEN_ORDERS)

    // publish to seperate feed, not chat.
    //sendChat('cancelled order: '+JSON.stringify(event) );
    displayPositions(false,SITE_POSITIONS);
    displayPositions(true,SITE_POSITIONS);
    OPEN_ORDERS = _.reject(OPEN_ORDERS, function (ord) {return ord['order_id']== event['order'];});
    displayOrders(false,OPEN_ORDERS);
    displayOrders(true,OPEN_ORDERS);
    //reload position tableS
    //make some sort of notification to user
}

function onTrade(topicUri, event) {
    //must get rid of safe price rpc!
    getSafePrices(Object.keys(MARKETS));


    console.log('in onTrade', SITE_TICKER, topicUri, event);
	now = new Date().toLocaleTimeString();
	updateTradeTable([now, event['price'], event['quantity'] ]);
	//TRADE_HISTORY.push(event['price']

//    if (SITE_TICKER in JSON.parse(event)) {
//        console.log('got event');
//        //todo: find where needed
//        orderBook(SITE_TICKER);
//        getTradeHistory(SITE_TICKER);
//    }

}


//subscribe functions (may want to put intial rpc call in them as well)

function subToTradeStream(ticker) {   
	console.log(trade_URI+ticker ,onTrade);
	session.subscribe(trade_URI+ticker ,onTrade);
}

function subToSafePrice(ticker) {   
	console.log(safe_prices_URI+ticker ,onSafePrice);
	session.subscribe(safe_prices_URI+ticker ,onSafePrice);
}

function subToOrderBook(ticker) {   
	console.log(order_book_URI+ticker, onBookUpdate);
	session.subscribe(order_book_URI+ticker, onBookUpdate);
}

function subToOpenOrders(id) {   
	console.log(open_orders_URI + id, onOpenOrder);
	session.subscribe(open_orders_URI + id, onOpenOrder);
}

function subToFills(id) {   
	console.log(fills_URI + id, onFill);
	session.subscribe(fills_URI + id, onFill);
}

function subToCancels(id) {   
	console.log(cancels_URI + id, onCancel);
	session.subscribe(cancels_URI + id, onCancel);
}

function sendChat(message) {
    session.publish(chat_URI, message, false)
}

function setSiteTicker(ticker) {
//    try{
//        session.unsubscribe(safe_price_URI+"#"+SITE_TICKER);
//    } catch(e) {}

    SITE_TICKER = ticker;
//    session.subscribe(safe_price_URI+'#'+SITE_TICKER, onSafePrice);
    $('.contract_unit').text(MARKETS[SITE_TICKER]['contract_type'] == 'futures' ? '฿' : '%');
}


//currency functions

function deposit() {
    getCurrentAddress();
    $('#depositModal').modal('show');
}

function withdrawModal() {
    $('#withdrawModal').modal('show');
}

function calculateMargin(positions, open_orders, safe_prices) {
    var low_margin = 0;
    var high_margin = 0;
    var margins = {};

    for (var key in positions) {
        var position = positions[key];

        if (position.contract_type == 'cash')
            continue;

        /*todo:temporary hack, resolve this more cleanly...
         what happens if we have positions in an inactive market?
         */
        if (!(position.ticker in MARKETS))
            continue;

        var max_position = position.position;
        var min_position = position.position;
        for (var j = 0; j < open_orders.length; ++j) {
            var order = open_orders[j];
            if (order.ticker == position.ticker) {
                if (order.side == 'BUY')
                    max_position += order.quantity;
                if (order.side == 'SELL')
                    min_position -= order.quantity;
            }
        }

        if (MARKETS[position.ticker].contract_type == 'futures') {
            var safe_price = safe_prices[position.ticker];
            var low_max = Math.abs(max_position) * MARKETS[position.ticker].margin_low * safe_price / 100 +
                max_position * (position.reference_price - safe_price);
            var low_min = Math.abs(min_position) * MARKETS[position.ticker].margin_low * safe_price / 100 +
                min_position * (position.reference_price - safe_price);
            var high_max = Math.abs(max_position) * MARKETS[position.ticker].margin_high * safe_price / 100 +
                max_position * (position.reference_price - safe_price);
            var high_min = Math.abs(min_position) * MARKETS[position.ticker].margin_high * safe_price / 100 +
                min_position * (position.reference_price - safe_price);

            high_margin += Math.max(high_max, high_min);
            low_margin += Math.max(low_max, low_min);
            margins[position.ticker] = [Math.max(high_max, high_min), Math.max(low_max, low_min)];
        }
        if (MARKETS[position.ticker].contract_type == 'prediction') {

            var payoff = MARKETS[position.ticker].final_payoff;
            var max_spent = 0;
            var max_received = 0;

            for (var j = 0; j < open_orders.length; ++j) {
                var order = open_orders[j];
                if (order.ticker == position.ticker) {
                    if (order.side == 'BUY')
                        max_spent += order.quantity * order.price;
                    if (order.side == 'SELL')
                        max_received += order.quantity * order.price;
                }
            }

            var worst_short_cover = Math.max(-min_position, 0) * payoff;
            var best_short_cover = Math.max(-max_position, 0) * payoff;

            var additional_margin = Math.max(max_spent + best_short_cover, -max_received + worst_short_cover);
            low_margin += additional_margin;
            high_margin += additional_margin;
            margins[position.ticker] = [additional_margin, additional_margin];
        }
    }
    margins['total'] = [low_margin, high_margin];
    return margins;
    //return [low_margin, high_margin];
}

//charting functions:
function decimalPlacesNeeded(denominator) {
    var factor_five = 0;
    var factor_two = 0;
    while (denominator % 5 == 0) {
        ++factor_five;
        denominator /= 5;
    }
    while (denominator % 2 == 0) {
        ++factor_two;
        denominator /= 2;
    }
    return Math.max(factor_five, factor_two);
}

function stackBook(book) {
    var newBook = [];

    book.sort(function (a, b) {
        return parseFloat(a[0]) - parseFloat(b[0])
    });

    if (book.length == 0)
        return [];

    var price = book[0][0];
    var quantity = book[0][1];

    for (var i = 1; i < book.length; i++) {
        if (book[i][0] == price) {
            quantity += book[i][1];
        } else {
            newBook.push([quantity, price]);
            price = book[i][0];
            quantity = book[i][1];
        }
    }
    newBook.push([quantity, price]);

    return newBook;
}

function build_trade_graph(trades) {
    var parseDate = d3.time.format("%Y-%m-%dT%H:%M:%S").parse;
    var data = [];

    // first, prepare the data to be in the cross-filter format
    for (var i = 0; i < trades.length; ++i) {
        data.push(
            {
                'date': parseDate(trades[i][0].split('.')[0]),
                'price': trades[i][1] / MARKETS[SITE_TICKER]['denominator'],
                'quantity': trades[i][2]
            });
    }
    var cd = crossfilter(data);
    var time_dimension = cd.dimension(function (d) {
        return d.date;
    });
    var volume_group = time_dimension.group().reduceSum(function (d) {
        return d.quantity;
    });
    var volume_weighted_price = time_dimension.group().reduce(
        // add
        function (p, v) {
            p.total_volume += v.quantity;
            p.price_volume_sum_product += v.price * v.quantity;
            p.volume_weighted_price = p.price_volume_sum_product / p.total_volume;
            return p;
        },
        // remove
        function (p, v) {
            p.total_volume -= v.quantity;
            p.price_volume_sum_product -= v.price * v.quantity;
            p.volume_weighted_price = p.price_volume_sum_product / p.total_volume;
            return p;
        },
        // init
        function () {
            return {'total_volume': 0, 'price_volume_sum_product': 0, 'volume_weighted_price': NaN}
        }
    );

    var priceChart = dc.compositeChart("#monthly-move-chart");
    var volumeChart = dc.barChart("#monthly-volume-chart");

    var numberFormat = d3.format(".2f");
    var dateFormat = d3.time.format("%Y-%M-%dT%H:%M:%S");

    priceChart.width(700)
        .height(180)
        .transitionDuration(1000)
        .margins({top: 10, right: 50, bottom: 25, left: 40})
        .dimension(time_dimension)
        .group(volume_weighted_price)
        .valueAccessor(function (d) {
            return d.value.volume_weighted_price;
        })
        .mouseZoomable(true)
        .x(d3.time.scale().domain([data[0]['date'], data[data.length - 1]['date']]))
        .round(d3.time.minutes.round)
        .xUnits(d3.time.minutes)
        .elasticY(true)
        .yAxisPadding("20%")
        .renderHorizontalGridLines(true)
        .brushOn(false)
        .rangeChart(volumeChart)
        .compose([
            dc.lineChart(priceChart).group(volume_weighted_price)
                .valueAccessor(function (d) {
                    return d.value.volume_weighted_price;
                })
                .renderArea(true)
        ])
        .xAxis();

    volumeChart.width(700)
        .height(50)
        .margins({top: 0, right: 50, bottom: 20, left: 40})
        .dimension(time_dimension)
        .group(volume_group)
        .centerBar(true)
        .gap(1)
        .x(d3.time.scale().domain([data[0]['date'], data[data.length - 1]['date']]))
        .round(d3.time.minute.round)
        .xUnits(d3.time.minutes);

    dc.renderAll();

}

function displayPrice(price, denominator, tick_size, contract_type) {
    var contract_unit = '฿';
    var percentage_adjustment = 1;
    if (contract_type == 'prediction') {
        contract_unit = '%';
        percentage_adjustment = 100;
    }
    var dp = decimalPlacesNeeded(denominator / ( percentage_adjustment * tick_size));

    /*
     console.log(contract_type) ;
     console.log(price) ;
     console.log( ((price * percentage_adjustment)/ denominator ).toFixed(dp)+ ' ' + contract_unit);
     */
    return ((price * percentage_adjustment) / denominator).toFixed(dp) + ' ' + contract_unit;

}
function updateOrderBook(book, full_size) {
	for (key in book){
			book = book[key];	
            var buyBook = [];
            var sellBook = [];

            var denominator = MARKETS[key]['denominator'];
            var tick_size = MARKETS[key]['tick_size'];
            var contract_type = MARKETS[key]['contract_type'];
            //var dp = decimalPlacesNeeded(denominator * percentage_adjustment / tick_size);

            for (var i = 0; i < book.length; i++) {
                var price = Number(book[i]['price']);
                var quantity = book[i]['quantity'];
                ((book[i]['order_side'] == 0) ? buyBook : sellBook).push([price , quantity]);
            }

            console.log(buyBook);
            buyBook = stackBook(buyBook);
            sellBook = stackBook(sellBook);

            sellBook.reverse();
           /*
           if(!full_size){
                buyBook = buyBook.slice(0,10)
                sellBook = sellBook.slice(0,10)
           }
           */
            console.log(buyBook);
            graphTable(buyBook, "buy", ORDER_BOOK_VIEW_SIZE);
            graphTable(sellBook, "sell", ORDER_BOOK_VIEW_SIZE);
	}
}

function updateTradeTable(trade) {
	var direction = '';

	if (trade[1] > TRADE_HISTORY[0][1]) {
		direction = 'success';
	} else if (trade[1] < TRADE_HISTORY[0][1]) {
		direction = 'error';
	} /*else {
		direction = 'neutral';
	}*/

	$('#tradeHistory tr:first').after("<tr class=" + direction + ">" +
		"<td>" + displayPrice(trade[1], MARKETS[SITE_TICKER]['denominator'], MARKETS[SITE_TICKER]['tick_size'], MARKETS[SITE_TICKER]['contract_type']) + "</td>" + // don't show ticker unless needed
		"<td>" + trade[2] + "</td>" +
		"<td>" + trade[0] + "</td>" +
		"</tr>");

	TRADE_HISTORY.push(trade);  //vs. unshift() ...?
}

function tradeTable(trades, fullsize) {
    console.log('in tradeTable');

    var length = fullsize ? trades.length : 25;
    $('#tradeHistory').empty()

    var direction = 'neutral';
    if (!fullsize) {trades = trades.slice(0,25)};

    trades.reverse();   /*trades.reverse is called again after the for loop.
                         trying to get the order right.*/

    for (var i = 1; i < trades.length; i++) {
        console.log(direction);
        console.log(i);
        console.log(trades[i]);

        console.log(trades[i][1] , trades[i - 1][1]);
        if (trades[i][1] > trades[i - 1][1]) {
            direction = 'success';
        } else if (trades[i][1] < trades[i - 1][1]) {
            direction = 'error';
        } /*else {
            direction = 'neutral';
        }*/


        console.log(direction);
        $('#tradeHistory').prepend("<tr class=" + direction + ">" +
            "<td>" + displayPrice(trades[i][1], MARKETS[SITE_TICKER]['denominator'], MARKETS[SITE_TICKER]['tick_size'], MARKETS[SITE_TICKER]['contract_type']) + "</td>" + // don't show ticker unless needed
            "<td>" + trades[i][2] + "</td>" +
            "<td>" + new Date(trades[i][0]).toLocaleTimeString() + "</td>" +
            "</tr>");
    }
    trades.reverse();


    $('#tradeHistory').prepend('<tr><th>Price <p class=\'contract_unit\'></p> </th><th>Vol.</th><th>Time</th></tr>');

    $('#tradeHistory').append(
        fullsize ?
            '<tr><td colspan="3"><button id="lessTrades" class="btn btn-block"><i class="icon-chevron-up"/></button></td></tr>' :
            '<tr><td colspan="3"><button id="moreTrades" class="btn btn-block"><i class="icon-chevron-down"/></button></td></tr>'
    );

    $('#lessTrades').click(function () {
        tradeTable(TRADE_HISTORY, false);
    });

    $('#moreTrades').click(function () {
        tradeTable(TRADE_HISTORY, true);
    });
}

function suggestOrder() {
        $('#psell').val(PSELL);
        $('#qsell').val(QSELL);
        $('#pbuy').val(PBUY);
        $('#qbuy').val(QBUY);
};

function graphTable(table, side, fullsize) {
//    if (fullsize) {
//        length = trades.length;
//    } else {
//        length = 10;
//    }
    var length = fullsize ? table.length : 10;
    console.log('in graphTable');
    console.log(fullsize);
    console.log(length);
    var id = (side == 'buy') ? '#orderBookBuys' : '#orderBookSells';

	var denominator = MARKETS[SITE_TICKER]['denominator'];
	var contract_type = MARKETS[SITE_TICKER]['contract_type'];
	var tick_size = MARKETS[SITE_TICKER]['tick_size'];

    $(id).empty();
	
    // update the suggested buy/sell orders:
    if (table.length >0) {
        if (side =='buy') {
            PSELL = displayPrice(table[table.length - 1][1], denominator, tick_size, contract_type).split(' ')[0];
            QSELL = table[table.length - 1][0];
        } else {
            PBUY = displayPrice(table[table.length - 1][1], denominator, tick_size, contract_type).split(' ')[0];
            QBUY = table[table.length - 1][0];
        }
    }

    for (var i = 0; i < Math.max(10,length); i++) {
        if (i < table.length) {
            //ugly reversing of table.. meh, it's working..
            var j = table.length - i -1;
            var price_cell = "<td>" + displayPrice(table[j][1], denominator, tick_size, contract_type) + "</td>";
            var quantity_cell = "<td>" + table[j][0] + "</td>";
            var row_string = (side == 'buy' ? quantity_cell + price_cell : price_cell + quantity_cell);
            $(id).append("<tr id='" + side + "_" + i + "'>" + 
							row_string + "</tr>");

			// highlight user's orders
            /*
            console.log('highlight user orders');
            console.log(table[i][1]);
            console.log(OPEN_ORDERS);
            console.log(_.pluck(OPEN_ORDERS,table[i][1] ))
            console.log(_.contains(_.pluck(OPEN_ORDERS,'price'),table[i][1] ));
            */
			if (_.contains(
                            _.pluck(
                                    _.filter(OPEN_ORDERS, function (order){return order['ticker']==SITE_TICKER;})
                                    ,'price')
                            ,table[j][1] )
               ) {
				$('#' + side + '_' + i).addClass("info");
			}
        }
        else {
            $(id).append("<tr><td> - </td><td> - </td></tr>");
        }
    }

    // add headers

    var price_header = "<th>" + (side == 'buy' ? "Bid" : "Ask") + "<p class='contract_unit'></p> </th>";
    var volume_header = "<th>Volume</th>";

    $(id).prepend("<tr>" + (side == 'buy' ? volume_header + price_header : price_header + volume_header) + "</tr>");

    $(id).append(
        fullsize ?
            '<tr><td colspan="2"><button  class="lessOrderBook btn btn-block"><i class="icon-chevron-up"/></button></td></tr>' :
            '<tr><td colspan="2"><button  class="moreOrderBook btn btn-block"><i class="icon-chevron-down"/></button></td></tr>'
    );

    $('.lessOrderBook').click(function () {
        console.log('less');
        ORDER_BOOK_VIEW_SIZE = false;
        updateOrderBook(ORDER_BOOK,ORDER_BOOK_VIEW_SIZE);
    });

    $('.moreOrderBook').click(function () {
        console.log('more');
        ORDER_BOOK_VIEW_SIZE = true;
        updateOrderBook(ORDER_BOOK,ORDER_BOOK_VIEW_SIZE);
    });
}

function displayOrders(show_all_tickers, orders) {
    var element = show_all_tickers ? '#openOrders' : '#market_order_table';
//    var margins = calculateMargin(SITE_POSITIONS, OPEN_ORDERS, SAFE_PRICES);
    $(element).empty()
        .append("<tr>" +
            (show_all_tickers ? "<th>Ticker</th>" : "") +
            "<th>"+ (show_all_tickers?"Quantity":"#") +"</th>" +
            "<th>Price</th>" +
            "<th>Buy/Sell</th>" +
            "<th>Cancel</th>" +
//            "<th>Reserved</th>" +
            "</tr>");

    _.each(_.groupBy(OPEN_ORDERS, function (orders) {return orders['ticker'];}),
        function (contract_group, ticker) {
            var length = _.size(contract_group);

            if (show_all_tickers || ticker == SITE_TICKER) { // if this SITE_TICKER is to be shown

                var ticker_td = (show_all_tickers ? "<td rowspan='" + length + "' style='vertical-align:middle' onclick='switchToTrade(\""+ ticker +"\")'>" + ticker  + "</td>" : "") // don't show ticker unless needed
//                var margin_td = (show_all_tickers ? "<td rowspan='" + length + "'>" + margins[ticker][1] / 1e8 + "</td>" : "") // don't show ticker unless needed
                var printed_ticker;
                _.each(contract_group, function (order) {
                    var quantity = order['quantity'];
                    var price = displayPrice(
                        order['price'],
                        MARKETS[order['ticker']]['denominator'],
                        MARKETS[order['ticker']]['tick_size'],
                        MARKETS[order['ticker']]['contract_type']);
                       
                    $(element).append("<tr id='cancel_order_row_" + order['order_id'] + "'>" +

                        (printed_ticker?'':ticker_td) +
                        "<td>" + quantity + "</td>" +
                        "<td nowrap>" + price + "</td>" +
                        "<td>" + order['side'] + "</td>" +
                        "<td>" +
                        "<button id='cancel_button_" + order['order_id'] + "' class='btn btn-block btn-danger' type='button' onclick='cancelOrder(" + order['order_id'] + ")'>" + (show_all_tickers?'cancel':'') + "<i class='icon-trash'/></button>" +
                        "</td>" +
                        "</tr>");
                    printed_ticker = true;
                });
            }
       });
}

function displayCash(display_account_page, positions) {
    var element = display_account_page ? '#account_cash_table' : '#cash_table';
    var margins = calculateMargin(SITE_POSITIONS, OPEN_ORDERS, SAFE_PRICES);
    $(element).empty()
        .append("<tr>" +
            "<th>Currency</th>" +
            "<th>Position</th>" +
            //"<th>Low Margin</th>" +
            "<th>Reserved in Margin</th>" +
            (display_account_page ?  "<th>Withdraw</th><th>Deposit</th>":"")
            + "</tr>");

    for (var key in positions) {
        $(element).append("<tr>" +
            "<td>" + positions[key]['ticker'] + "</td>" + 
            "<td>" + (positions[key]['position'] / 1e8) + "</td>" +
            //"<td>" + margins['total'][0] / 1e8 + "</td>" +
            "<td>" + margins['total'][1] / 1e8 + "</td>" +
            
            (display_account_page?
            "<td>" +
            "<button onclick='withdrawModal()' class='btn btn-block' type='button'>" +
            " <i class='icon-minus-sign'/>" +
            "</button>" +
            "</td>" +
            "<td>" +
            "<button onclick='deposit()' class='btn btn-block' type='button'>" +
            " <i class='icon-plus-sign'/>" +
            "</button>" +
            "</td>" 
            : "")


            + "</tr>");
    }
}

function displayPositions(show_all_tickers, positions) {
    var element = show_all_tickers ? '#account_positions_table' : '#market_position_table';
    var margins = calculateMargin(SITE_POSITIONS, OPEN_ORDERS, SAFE_PRICES);
    $(element).empty()
        .append("<tr>" +
            (show_all_tickers ? "<th>Ticker</th>" : "") +
            "<th>Position</th>" +
			//<th>Low Margin</th>
			"<th>Reserved for Margin</th></tr>");

    // remove cash and old inactive positions
    positions = _.reject(positions, function (contract) {return contract['contract_type'] =='cash';});
    // using the underscore library function _.indexOf() as IE doesn't support the standard Array.indexOf().  Haven't actually checked - Just hoping.
    positions = _.filter(positions, function (contract) {return _.indexOf(Object.keys(margins), contract['ticker'])>-1;});

    for (var key in positions) {
        if (show_all_tickers || (positions[key]['ticker'] == SITE_TICKER)) {// if this ticker is to be shown
            var ticker = positions[key]['ticker'];//(typeof positions[key]['ticker'] =='number')?SITE_POSITIONS[ticker]['ticker']:positions[key]['ticker']
            /*
            console.log('the key',key);
            console.log('the position array', positions);
            console.log('omfg fuck you ticker',ticker);
            console.log('margins',margins);
            */
    //		console.log(ticker == SITE_TICKER);
    //		console.log(element);
            $(element).append("<tr>" +
                (show_all_tickers ? "<td onclick='switchToTrade(\""+ ticker +"\")' >" + ticker + "</td>" : "") + // don't show ticker unless needed
                "<td>" + positions[key]['position'] + "</td>" +
                //"<td>" + margins[ticker][1] / 1e8 + "</td>" +
                "<td>" + margins[ticker][0] / 1e8 + "</td>" +
                "</tr>");
    //			console.log("<tr>" +
    //            (show_all_tickers ? "<td onclick='switchToTrade(\""+ ticker +"\")' >" + ticker + "</td>" : "") + // don't show ticker unless needed
    //            "<td>" + positions[key]['position'] + "</td>" +
    //            //"<td>" + margins[ticker][1] / 1e8 + "</td>" +
    //            "<td>" + margins[ticker][0] / 1e8 + "</td>" +
    //            "</tr>")
            }
    }
}

function marketsToDisplayTree(markets) {
    var displayMarket = {};
    displayMarket['key'] = 'Markets';
    displayMarket['values'] = [];

    var futures = {};
    var predictions = {};
    var myMarkets = {};

    futures['key'] = 'Futures';
    predictions['key'] = 'Predictions';
    myMarkets['key'] = 'My Markets';

    futures['values'] = [];
    predictions['values'] = [];
    myMarkets['values'] = [];


    for (key in markets) {
        var entry = {
            'key': markets[key]['description'],
            'ticker': key,
            'action': key
        };
        (markets[key]['contract_type'] == 'futures' ? futures : predictions)['values'].push(entry);

        if (true)           // todo: check for markets the user has positions on.
            myMarkets['values'].push(entry)
    }

    displayMarket['values'].push(futures);
    displayMarket['values'].push(predictions);
    displayMarket['values'].push(myMarkets);

    return [displayMarket];
}

function welcome (MARKETS) {
    var markets = MARKETS;
    $('#welcome').empty()

        $('#welcome').append("<thead><tr>" +
            "<th>Active Markets</th>" +
            "<th>Description</th>" +
            "</tr></thead>");

    for (row in markets) {

        console.log("<tr>" + "<td>"+ row + "</td>" + "<td>" + markets[row]['description'] + "</td>" + "</tr>");
        $('#welcome').append("<tr onclick='switchToTrade(\""+ row +"\")' >" +
            "<td>"+ row + "</td>" +
            "<td>" + markets[row]['description'] + "</td>" +
            "</tr>");

    }

}

function tree(datafunction) {
    nv.addGraph(function () {
        var chart = nv.models.indentedTree()
            .tableClass('table table-striped') //for bootstrap styling
            .columns([
                {
                    key: 'key',
                    label: 'Name',
                    showCount: true,
                    width: '75%',
                    type: 'text'
                },
                {
                    key: 'ticker',
                    label: 'Ticker',
                    width: '25%',
                    type: 'text',
                    classes: function (d) {
                        return d.action ? 'clickable name' : 'name';
                    },
                    click: function (d) {
                        if (d.action) {
                            switchToTrade(d.action);
                            //setSiteTicker(d.action);
                            //$('#Trade').click();
                        }
                    }
                }
            ]);
        d3.select('#tree')
            .datum(datafunction)
            .call(chart);
        return chart;
    });
}


function switchToTrade (new_ticker) {

    //need to fix this hardcoding
    id = SITE_TICKER=='USD.13.7.31'?17:16; 

    if (logged_in) {
        try{session.unsubscribe(order_book_URI+SITE_TICKER, onBookUpdate);}
            catch(err){console.log(err);}
        try{session.unsubscribe(trade_URI+SITE_TICKER,onTrade);}
            catch(err){console.log(err);}
        try{ session.unsubscribe(safe_prices_URI+SITE_TICKER ,onSafePrice);}
            catch(err){console.log(err);}
    }

    /*
    try{session.unsubscribe(cancels_URI + user_id, onCancel);}
        catch(err){console.log(err);}
    try{session.unsubscribe(fills_URI + user_id, onFill);}
        catch(err){console.log(err);}
    try{ session.unsubscribe(open_orders_URI + user_id, onOpenOrder);}
        catch(err){console.log(err);}
    */

	setSiteTicker(new_ticker);

    id = SITE_TICKER=='USD.13.7.31'?17:16; 

	try{session.subscribe(order_book_URI+SITE_TICKER, onBookUpdate);}
        catch(err){console.log(err);}
	try{session.subscribe(trade_URI+SITE_TICKER,onTrade);}
        catch(err){console.log(err);}
    try{ session.subscribe(safe_prices_URI+SITE_TICKER ,onSafePrice);}
        catch(err){console.log(err);}

	$('#Trade').click();
}

//Notification messages
var notifications = new Object();

notifications.orderError = function () {
    alert('Order error: must be between 0.0% and 100.0%');
};
notifications.processing = function (msg) {
    $('#processingModal').modal('show');
};
notifications.dismiss_processing = function (msg) {
    $('#processingModal').modal('hide');
};


$('#Trade').click(function () {
    $('#currentMarket').html(MARKETS[SITE_TICKER]['description']);
    $('#currentTicker').html(SITE_TICKER);
    $('#descriptionText').html(MARKETS[SITE_TICKER]['full_description']);

    getTradeHistory(SITE_TICKER);
    orderBook(SITE_TICKER);

    if (logged_in) {
        getOpenOrders();
        getPositions();
    }
    //suggestOrder();

});

$('#Account').click(function () {
    getPositions();
    getOpenOrders();
    if (!logged_in) {
        $('#loginButton').click()
    }
});

$('#logoutButton').click(function () {
    logout();

    $('#loginstatus').hide();
    $('#logoutButton').hide();

    $('#loginButton').show();
    $('#registeration').show()
});

$('#registerButton').click(function () {
    console.log(registerPassword.value);
    makeAccount(registerLogin.value, registerPassword.value, registerEmail.value, registerBitMessage.value);
});


function orderButton(q, p, s) {
    if (!logged_in) {
        $('#loginButton').click()
    } else {
        var ord = {};
        var price_entered = Number(p);
        ord['ticker'] = SITE_TICKER;
        ord['quantity'] = parseInt(q);
        var tick_size = MARKETS[SITE_TICKER]['tick_size'];
        var percentage_adjustment = (MARKETS[SITE_TICKER]['contract_type'] == 'prediction' ? 100 : 1);
        ord['price'] = Math.round((MARKETS[SITE_TICKER]['denominator'] * price_entered) / (percentage_adjustment * tick_size)) * tick_size;
        ord['side'] = s;
        placeOrder(ord);
    }
}

$('#sellButton').click(function () {
    orderButton(qsell.value, psell.value, 1);
    if (qsell.value.length ==0 ) {
       $('#processingModal').modal('hide');
       alert('Quantity must be non-zero');
    } 
});

$('#buyButton').click(function () {
    orderButton(qbuy.value, pbuy.value, 0);
    if (qbuy.value.length ==0 ) {
       $('#processingModal').modal('hide');
       alert('Quantity must be non-zero');
    } 
});

$('#chatButton').click(function () {
    sendChat(chatBox.value);
    $('#chatBox').val('');
});

$('#newAddressButton').click(function () {
    getNewAddress();
    getCurrentAddress();
});

$('#chatFooterButton').click(function () {
    $('.footer').collapse('toggle');
    $('input#chatBox.chatInput').focus();
    $('#chatFooterButton').hide();
});

$('#minimizeChat').click(function () {
    $('#chatFooterButton').show();
    $('.footer').collapse('toggle');
});

$('.global-modal').on('hidden', function() {
    //the global-modal class consists of: 'myModal' (login) and 'registerModal'
    if (!logged_in)
        $('#PennyArcade').click();

})

$('#PennyArcade').click(function () {
    //remove the outline of a tab
    $('li.active').removeAttr('class','active');
    welcome (MARKETS)
});

$("input#chatBox.chatInput").keypress(function (e) {
    var code = (e.keyCode ? e.keyCode : e.which);
    if (code == 13) {
        $('#chatButton').click();
    }
});

//modals

$('#myModal').on('shown', function () {
    $('#login').focus();
});

$('#registerModal').on('shown', function () {
    $('#registerLogin').focus();
});

//keypress
$("#login").keypress(function (e) {
    var code = (e.keyCode ? e.keyCode : e.which);
    if (code == 13) {
        $('#login_button').click();
    }
});

$("#password").keypress(function (e) {
    var code = (e.keyCode ? e.keyCode : e.which);
    if (code == 13) {
        $('#login_button').click();
    }
});

// responsive stuff

function controlPanelDisplay () {
    if ( $(window).width() < 1904) {
        $('#leftControlPanel').hide()
    } else {
        $('#leftControlPanel').show()
    }

}

$(window).load(controlPanelDisplay);

$(window).resize(controlPanelDisplay);
