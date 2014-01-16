var session = null;


var base_uri = "wss://sputnikmkt.com:8000/";
var get_chat_history_URI = base_uri + "procedures/get_chat_history";

var safe_price_URI = base_uri + "safe_price";
var get_safe_prices_URI = base_uri + "procedures/get_safe_prices";
var place_order_URI = base_uri + "procedures/place_order";
var get_trade_history_URI = base_uri + "procedures/get_trade_history";
var markets_URI = base_uri + "procedures/list_markets";
var positions_URI = base_uri + "procedures/get_positions";
var get_order_book_URI = base_uri + "procedures/get_order_book";
var make_account_URI = base_uri + "procedures/make_account";
var get_open_orders_URI = base_uri + "procedures/get_open_orders";
var cancel_order_URI = base_uri + "procedures/cancel_order";

var register_two_factor_URI= base_uri + "procedures/register_two_factor";
var get_new_two_factor_URI= base_uri + "procedures/get_new_two_factor";
var disable_two_factor_URI= base_uri + "procedures/disable_two_factor";

var get_profile_URI = base_uri + "procedures/get_profile"
var change_profile_URI = base_uri + "procedures/change_profile"

var change_password_URI = base_uri + "procedures/change_password";
var get_new_address_URI = base_uri + "procedures/get_new_address";
var get_current_address_URI = base_uri + "procedures/get_current_address";
var withdraw_URI = base_uri + "procedures/withdraw";

var get_cookie_URI = base_uri + "procedures/get_cookie";
var logout_URI = base_uri + "procedures/logout";

var AUTHEXTRA = {"keylen": 32, "salt": "RANDOM SALT", "iterations": 1000};



function get_profile() {
    session.call(get_profile_URI).then(
        function (profile) {
            console.log(profile);
            $('#nickname').text(profile.nickname)
            $('#email').text(profile.email)
        }
    )
}
function change_profile(new_nickname, new_email) {
    session.call(change_profile_URI, new_nickname, new_email).then(
        function(res) {
            if(res) {
                alert('success!');
                $('#nickname').text(new_nickname);
                $('#email').text(new_email);
            }
            else
            {
                alert('profile change failed')
            }
        }
    )
}

// connect to Autobahn.ws
function connect() {
    //ws -> wss
    var wsuri;// = "wss://" + host + ":9000";

    if (window.location.protocol === "file:") {
        wsuri = "wss://localhost:8000";
        //wsuri = "ws://localhost:9000";
    } else {
        wsuri = "wss://" + window.location.hostname + ":8000";
        //wsuri = "ws://" + window.location.hostname + ":9000";
    }
    ab.connect(wsuri,
        function (sess) {
            session = sess;
            ab.log("connected to " + wsuri);
            onConnect();
        },

        function (code, reason, detail) {
            //alert('disconnected!!!');
            $('#loggedOut').modal('show');
            logout();
            session = null;
            switch (code) {
                case ab.CONNECTION_UNSUPPORTED:
                    window.location = "https://autobahn.ws/unsupportedbrowser";
                    break;
                case ab.CONNECTION_CLOSED:
                    window.location.reload();
                    break;
                default:
                    ab.log(code, reason, detail);
                    break;
            }
        },

        {'maxRetries': 1, 'retryDelay': 1000}
    );
}

function cookie_login(cookie) {
    parts = cookie.split("=", 2);
    parts = parts[1].split(":", 2);
    name = parts[0];
    uid = parts[1];
    if (!uid)
        return failed_cookie("bad cookie. clearing.")
    session.authreq(uid).then(function (challenge) {
        authextra = JSON.parse(challenge).authextra
        authextra.salt = "cookie"
        console.log(ab.deriveKey("cookie", authextra));

        var secret = ab.deriveKey("cookie", authextra);

        var signature = session.authsign(challenge, secret);
        console.log(signature)

        session.auth(signature).then(function() {login.value = name; onAuth();}, failed_cookie);
        console.log('end of cookie_login');
    }, function (err) {
        failed_cookie('error processing cookie login');
    });
}

function do_login(login, password) {
    session.authreq(login /*, extra*/).then(function (challenge) {
        AUTHEXTRA = JSON.parse(challenge).authextra
        console.log('challenge', JSON.parse(challenge).authextra);
        console.log( ab.deriveKey(password, JSON.parse(challenge).authextra));
        console.log(two_factor.value);

        var secret = ab.deriveKey(password, JSON.parse(challenge).authextra);

        if (two_factor.value != "")
        {
            secret = ab.deriveKey(secret,
                {'iterations':10, 'keylen':32, 'salt':two_factor.value})
        }

        console.log(challenge);
        console.log( session.authsign(challenge, secret) );
        var signature = session.authsign(challenge, secret);
        console.log(signature)

        session.auth(signature).then(onAuth, failed_login);//ab.log);
        console.log('end of do_login');
    }, function (err) {
        failed_login('bad login');
    });
}

$('#do_login_button').click(function(){
    do_login(login.value, password.value);
});

function failed_cookie(err)
{
    document.cookie = "";
    console.log(err)
}

function failed_login(err) {
    /*bootstrap gets stuck if if two modals are called in succession, so force
    the removal of shaded background with the following line */
    $('.modal-backdrop').removeAttr('class','in')

    //add a notification of failed login to login error modal then restart modal
    $('#login_error').attr('class','alert')
                     .text('Login error, please try again.');
    $('#loginButton').click();
};

function logout() {
    logged_in = false;
    $('#loggedInMenu').hide();
    $('#dLabel').text('');

    $('#loginButton').show();
    $('#registration').show();
    $('#Sputnik').click();

    //clear user data:
    $('.table').empty()
    SITE_POSITIONS = [];
    OPEN_ORDERS = [];
    AUTHEXTRA = {"keylen": 32, "salt": "RANDOM SALT", "iterations": 1000};
    console.log(OPEN_ORDERS);
    //need to unsubscribe from everything.

    session.call(logout_URI);
    session.close();
    connect();
}

function getTradeHistory(ticker) {
    var contract_unit = ' ฿';
    var now = new Date();
    var then = new Date(now.getTime());

    then.setDate(now.getDate() - 7);

    session.call(get_trade_history_URI, SITE_TICKER, 7 * 24 * 3600).then(
        function (trades) {
            build_trade_graph(trades);
            TRADE_HISTORY = trades.reverse();
            tradeTable(TRADE_HISTORY, true);
        })
}

function getChatHistory() {
    session.call(get_chat_history_URI).then(
        function(chats) {
            for (chat in chats){
                CHAT_MESSAGES.push(chats[chat]);
            }

            $('#chatArea').html(CHAT_MESSAGES.join('\n'));
            $('#chatArea').scrollTop($('#chatArea')[0].scrollHeight);
        })
}

function placeOrder(order) {
    notifications.processing(order);
    session.call(place_order_URI, order).then(
        function (order_status) {
            notifications.dismiss_processing(order_status)
            if (order_status == false) {
                notifications.orderError();
            }
        }
    );

}

function cancelOrder(cancel) {
    session.call(cancel_order_URI, cancel).then(
        function (res) {
            $('#cancel_order_row_' + cancel).addClass('warning');
            $('#cancel_button_' + order_id).attr('disabled', 'disabled')
                .removeClass('btn-danger');
            //todo: this is disgusting, change that.  Agreed.
            //setTimeout(getOpenOrders, 1000);
        })
}

function getPositions() {
    session.call(positions_URI).then(
        function (positions) {

            SITE_POSITIONS = positions;

            var cash_positions = Object()
            var contract_positions = Object()
            var open_tickers = _.pluck(OPEN_ORDERS,'ticker')

            for (var key in positions)
                if(positions[key]['contract_type'] == 'cash')  {
                    cash_positions[key] = positions[key];
                }else{
                if (positions[key]['position'] != 0 || _.contains(open_tickers, positions[key]['ticker']))
                    contract_positions[key] = positions[key];
                }


            displayCash(true, cash_positions);
            displayCash(false, cash_positions);
            displayPositions(true, contract_positions);
            displayPositions(false, contract_positions);
        });
}

function orderBook(ticker) {
    console.log('in orderBook');
    session.call(get_order_book_URI, ticker).then(
        function (book) {
            ORDER_BOOK = book;
            var buyBook = [];
            var sellBook = [];

            var denominator = MARKETS[ticker]['denominator'];
            var tick_size = MARKETS[ticker]['tick_size'];
            var contract_type = MARKETS[ticker]['contract_type'];
            //var dp = decimalPlacesNeeded(denominator * percentage_adjustment / tick_size);

            for (var i = 0; i < book.length; i++) {
                var price = Number(book[i]['price']);
                var quantity = book[i]['quantity'];
                ((book[i]['side'] == -1) ? buyBook : sellBook).push([price , quantity]);
            }

            buyBook = stackBook(buyBook);
            sellBook = stackBook(sellBook);

            sellBook.reverse();

            graphTable(buyBook, "buy",true);// ORDER_BOOK_VIEW_SIZE);
            graphTable(sellBook, "sell",true);//ORDER_BOOK_VIEW_SIZE);
            suggestOrder()
        }
    );
}

function withdraw() {
    session.call(withdraw_URI, 'BTC', withdrawAddress.value, Math.round(100000000 * Number(withdrawAmount.value))).then(
        function (res) {
            console.log(res);
        }
    )
}

$('#withdrawButton').click(function(){
    withdraw();
});


function getCurrentAddress() {
    session.call(get_current_address_URI).then(
        function (addr) {
            console.log(addr);
            $('#deposit_address').attr('href', "bitcoin:" + addr).text(addr);
            $('#qrcode').empty();
            $('#qrcode').qrcode("bitcoin:" + addr);
        }
    )
}

function change_password(old_password, new_password) {
    old_password_hash = ab.deriveKey(old_password,AUTHEXTRA);
    new_password_hash = ab.deriveKey(new_password,AUTHEXTRA);
    console.log(old_password_hash);
    session.call(change_password_URI,old_password_hash, new_password_hash).then(
        function (res) {
            if (res) {
                alert('success!');
                $('.modal').modal('hide');
            } else {
                alert('password reset failed');
            }

        }
    )
}

function getNewAddress() {
    session.call(get_new_address_URI).then(
        function (addr) {
            console.log(addr);
        }
    )
}

function registerTwoFactor(confirmation) {
    notifications.processing('confirmation');
    session.call(register_two_factor_URI, confirmation).then(
        function (res) {
            notifications.dismiss_processing(res)
            console.log(res);
            if (res) {
              two_factor.value = 'enabled';
              TWO_FACTOR_ON = true;
              twoFactorSetting();
            }
        }
    )
}

function disableTwoFactor(code) {
    session.call(disable_two_factor_URI, code).then(
        function(res) {
            if(res){
                console.log('disabled');
                two_factor.value = '';
                TWO_FACTOR_ON = false;
                twoFactorSetting();
            }
        })
}
function getNewTwoFactor() {
    session.call(get_new_two_factor_URI).then(
        function(secret) {
            console.log(secret);
            console.log("otpauth://totp/Sputnik:" + login.value +  "?secret=" + secret + "&issuer=SputnikMKT")
            $('#twoFactor').empty();
            new QRCode(document.getElementById("twoFactor"), "otpauth://totp/Sputnik:" + login.value + "?secret=" + secret + "&issuer=SputnikMKT");
        })
}

function getOpenOrders() {
    console.log('Making getOpenOrders RPC call');
    session.call(get_open_orders_URI).then(
        function (orders) {
            console.log('Ended RPC call, drawing');
            OPEN_ORDERS = orders
            displayOrders(true, orders);
            displayOrders(false, orders);
        }
    );
}

function getMarkets() {
    console.log('in getMarkets');
    session.call(markets_URI).then(
        function (res) {
            newMarketsToDisplay(res);
            MARKETS = res;

            //load up the splash page
            welcome (MARKETS);

            //load the active markets for search typeahead.
            $('#search').typeahead({source : _.keys(MARKETS)});

                // randomly select a default market
                var keys = [];
                for (key in MARKETS) {
                    if (MARKETS[key]['contract_type'] != 'cash')
                        keys.push(key)
                }
                setSiteTicker(keys[Math.floor((keys.length) * Math.random())]);
                // but actually for the demo!
                setSiteTicker('MXN/BTC');

            for (key in MARKETS)
                if (MARKETS[key].contract_type == 'futures')
                    session.subscribe(safe_price_URI + '#' + key, onSafePrice);
            console.log(SITE_TICKER);
        });
}

function getSafePrices() {
    session.call(get_safe_prices_URI, []).then(
        function (res) {
            SAFE_PRICES = res;
        }
    );
}

function makeAccount(name, psswd, email) {
    console.log('in make account');
    var salt = Math.random().toString(36).slice(2);
    AUTHEXTRA['salt'] = salt;

    var psswdHsh = ab.deriveKey(psswd, AUTHEXTRA );

    console.log('making session call for makeAccount');
    session.call(make_account_URI, name, psswdHsh, salt,  email).then(
        function (res) {
            login.value = registerLogin.value;
            if (res){
                do_login(registerLogin.value, registerPassword.value);
            } else {
                alert('Username is taken.');
            }
        })
}

function getCookie() {
    session.call(get_cookie_URI).then(
        function (uid) {
            console.log("cookie: ", uid);
            document.cookie = "login" + "=" + login.value + ":" + uid;
        }
    );
}

