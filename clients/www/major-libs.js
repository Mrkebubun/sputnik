/*
 AutobahnJS - http://autobahn.ws

 Copyright 2011, 2012 Tavendo GmbH.
 Licensed under the MIT License.
 See license text at http://www.opensource.org/licenses/mit-license.php

 AutobahnJS includes code from:

 when - http://cujojs.com

 (c) copyright B Cavalier & J Hann
 Licensed under the MIT License at:
 http://www.opensource.org/licenses/mit-license.php

 Crypto-JS - http://code.google.com/p/crypto-js/

 (c) 2009-2012 by Jeff Mott. All rights reserved.
 Licensed under the New BSD License at:
 http://code.google.com/p/crypto-js/wiki/License

 console-normalizer - https://github.com/Zenovations/console-normalizer

 (c) 2012 by Zenovations.
 Licensed under the MIT License at:
 http://www.opensource.org/licenses/mit-license.php

*/
(function(a){a||(a=window.console={log:function (topicUri){},info:function(){},warn:function(){},error:function(){}});Function.prototype.bind||(Function.prototype.bind=function(a){var d=this,e=Array.prototype.slice.call(arguments,1);return function(){return d.apply(a,Array.prototype.concat.apply(e,arguments))}});"object"===typeof a.log&&(a.log=Function.prototype.call.bind(a.log,a),a.info=Function.prototype.call.bind(a.info,a),a.warn=Function.prototype.call.bind(a.warn,a),a.error=Function.prototype.call.bind(a.error,
a));"group"in a||(a.group=function(b){a.info("\n--- "+b+" ---\n")});"groupEnd"in a||(a.groupEnd=function(){a.log("\n")});"time"in a||function(){var b={};a.time=function(a){b[a]=(new Date).getTime()};a.timeEnd=function(d){var e=(new Date).getTime();a.info(d+": "+(d in b?e-b[d]:0)+"ms")}}()})(window.console);/*
 MIT License (c) copyright 2011-2013 original author or authors */
(function(a){a(function(){function a(c,b,e,j){return d(c).then(b,e,j)}function d(a){return a instanceof c?a:i(a)?e(a):f(a)}function e(a){var c=k();try{a.then(function(a){c.resolve(a)},function(a){c.reject(a)},function(a){c.progress(a)})}catch(b){c.reject(b)}return c.promise}function c(a){this.then=a}function f(a){return new c(function(c){try{return d("function"==typeof c?c(a):a)}catch(b){return g(b)}})}function g(a){return new c(function(c,b){try{return d("function"==typeof b?b(a):g(a))}catch(e){return g(e)}})}
function k(){function a(c,b,d){return i(c,b,d)}function b(a){return l(d(a))}function e(a){return l(g(a))}function f(a){return n(a)}var p,s,h,i,n,l;p=new c(a);p={then:a,resolve:b,reject:e,progress:f,notify:f,promise:p,resolver:{resolve:b,reject:e,progress:f,notify:f}};s=[];h=[];i=function(a,c,b){var d,e;d=k();e="function"===typeof b?function(a){try{d.notify(b(a))}catch(c){d.notify(c)}}:function(a){d.notify(a)};s.push(function(b){b.then(a,c).then(d.resolve,d.reject,e)});h.push(e);return d.promise};
n=function(a){j(h,a);return a};l=function(a){i=a.then;l=d;n=m;j(s,a);h=s=r;return a};return p}function i(a){return a&&"function"===typeof a.then}function l(c,d,e,j,f){p(2,arguments);return a(c,function(c){function p(a){q(a)}function g(a){l(a)}var h,m,i,o,n,l,q,r,t,w;t=c.length>>>0;h=Math.max(0,Math.min(d,t));i=[];m=t-h+1;o=[];n=k();if(h){r=n.notify;q=function(a){o.push(a);--m||(l=q=s,n.reject(o))};l=function(a){i.push(a);--h||(l=q=s,n.resolve(i))};for(w=0;w<t;++w)w in c&&a(c[w],g,p,r)}else n.resolve(i);
return n.promise.then(e,j,f)})}function h(a,c,b,d){p(1,arguments);return n(a,m).then(c,b,d)}function n(c,d){return a(c,function(c){var e,j,f,p,h,g;f=j=c.length>>>0;e=[];g=k();if(f){p=function(c,j){a(c,d).then(function(a){e[j]=a;--f||g.resolve(e)},g.reject)};for(h=0;h<j;h++)h in c?p(c[h],h):--f}else g.resolve(e);return g.promise})}function j(a,c){for(var b,d=0;b=a[d++];)b(c)}function p(a,c){for(var b,d=c.length;d>a;)if(b=c[--d],null!=b&&"function"!=typeof b)throw Error("arg "+d+" must be a function");
}function s(){}function m(a){return a}var q,t,r;a.defer=k;a.resolve=d;a.reject=function(c){return a(c,g)};a.join=function(){return n(arguments,m)};a.all=h;a.map=n;a.reduce=function(c,d){var e=t.call(arguments,1);return a(c,function(c){var j;j=c.length;e[0]=function(c,e,f){return a(c,function(c){return a(e,function(a){return d(c,a,f,j)})})};return q.apply(c,e)})};a.any=function(a,c,b,d){return l(a,1,function(a){return c?c(a[0]):a[0]},b,d)};a.some=l;a.chain=function(c,d,e){var j=2<arguments.length;
return a(c,function(a){a=j?e:a;d.resolve(a);return a},function(a){d.reject(a);return g(a)},function(a){"function"===typeof d.notify&&d.notify(a);return a})};a.isPromise=i;c.prototype={always:function(a,c){return this.then(a,a,c)},otherwise:function(a){return this.then(r,a)},yield:function(a){return this.then(function(){return a})},spread:function(a){return this.then(function(c){return h(c,function(c){return a.apply(r,c)})})}};t=[].slice;q=[].reduce||function(a){var c,b,d,e,j;j=0;c=Object(this);e=
c.length>>>0;b=arguments;if(1>=b.length)for(;;){if(j in c){d=c[j++];break}if(++j>=e)throw new TypeError;}else d=b[1];for(;j<e;++j)j in c&&(d=a(d,c[j],j,c));return d};return a})})("function"==typeof define&&define.amd?define:function(a){"object"===typeof exports?module.exports=a():this.when=a()});var CryptoJS=CryptoJS||function(a,b){var d={},e=d.lib={},c=e.Base=function(){function a(){}return{extend:function(c){a.prototype=this;var b=new a;c&&b.mixIn(c);b.hasOwnProperty("init")||(b.init=function(){b.$super.init.apply(this,arguments)});b.init.prototype=b;b.$super=this;return b},create:function(){var a=this.extend();a.init.apply(a,arguments);return a},init:function(){},mixIn:function(a){for(var c in a)a.hasOwnProperty(c)&&(this[c]=a[c]);a.hasOwnProperty("toString")&&(this.toString=a.toString)},
clone:function(){return this.init.prototype.extend(this)}}}(),f=e.WordArray=c.extend({init:function(a,c){a=this.words=a||[];this.sigBytes=c!=b?c:4*a.length},toString:function(a){return(a||k).stringify(this)},concat:function(a){var c=this.words,b=a.words,d=this.sigBytes,a=a.sigBytes;this.clamp();if(d%4)for(var e=0;e<a;e++)c[d+e>>>2]|=(b[e>>>2]>>>24-8*(e%4)&255)<<24-8*((d+e)%4);else if(65535<b.length)for(e=0;e<a;e+=4)c[d+e>>>2]=b[e>>>2];else c.push.apply(c,b);this.sigBytes+=a;return this},clamp:function(){var c=
this.words,b=this.sigBytes;c[b>>>2]&=4294967295<<32-8*(b%4);c.length=a.ceil(b/4)},clone:function(){var a=c.clone.call(this);a.words=this.words.slice(0);return a},random:function(c){for(var b=[],d=0;d<c;d+=4)b.push(4294967296*a.random()|0);return new f.init(b,c)}}),g=d.enc={},k=g.Hex={stringify:function(a){for(var c=a.words,a=a.sigBytes,b=[],d=0;d<a;d++){var e=c[d>>>2]>>>24-8*(d%4)&255;b.push((e>>>4).toString(16));b.push((e&15).toString(16))}return b.join("")},parse:function(a){for(var c=a.length,
b=[],d=0;d<c;d+=2)b[d>>>3]|=parseInt(a.substr(d,2),16)<<24-4*(d%8);return new f.init(b,c/2)}},i=g.Latin1={stringify:function(a){for(var c=a.words,a=a.sigBytes,b=[],d=0;d<a;d++)b.push(String.fromCharCode(c[d>>>2]>>>24-8*(d%4)&255));return b.join("")},parse:function(a){for(var c=a.length,b=[],d=0;d<c;d++)b[d>>>2]|=(a.charCodeAt(d)&255)<<24-8*(d%4);return new f.init(b,c)}},l=g.Utf8={stringify:function(a){try{return decodeURIComponent(escape(i.stringify(a)))}catch(c){throw Error("Malformed UTF-8 data");
}},parse:function(a){return i.parse(unescape(encodeURIComponent(a)))}},h=e.BufferedBlockAlgorithm=c.extend({reset:function(){this._data=new f.init;this._nDataBytes=0},_append:function(a){"string"==typeof a&&(a=l.parse(a));this._data.concat(a);this._nDataBytes+=a.sigBytes},_process:function(c){var b=this._data,d=b.words,e=b.sigBytes,h=this.blockSize,g=e/(4*h),g=c?a.ceil(g):a.max((g|0)-this._minBufferSize,0),c=g*h,e=a.min(4*c,e);if(c){for(var i=0;i<c;i+=h)this._doProcessBlock(d,i);i=d.splice(0,c);b.sigBytes-=
e}return new f.init(i,e)},clone:function(){var a=c.clone.call(this);a._data=this._data.clone();return a},_minBufferSize:0});e.Hasher=h.extend({cfg:c.extend(),init:function(a){this.cfg=this.cfg.extend(a);this.reset()},reset:function(){h.reset.call(this);this._doReset()},update:function(a){this._append(a);this._process();return this},finalize:function(a){a&&this._append(a);return this._doFinalize()},blockSize:16,_createHelper:function(a){return function(c,b){return(new a.init(b)).finalize(c)}},_createHmacHelper:function(a){return function(c,
b){return(new n.HMAC.init(a,b)).finalize(c)}}});var n=d.algo={};return d}(Math);(function(){var a=CryptoJS,b=a.lib.WordArray;a.enc.Base64={stringify:function(a){var b=a.words,c=a.sigBytes,f=this._map;a.clamp();for(var a=[],g=0;g<c;g+=3)for(var k=(b[g>>>2]>>>24-8*(g%4)&255)<<16|(b[g+1>>>2]>>>24-8*((g+1)%4)&255)<<8|b[g+2>>>2]>>>24-8*((g+2)%4)&255,i=0;4>i&&g+0.75*i<c;i++)a.push(f.charAt(k>>>6*(3-i)&63));if(b=f.charAt(64))for(;a.length%4;)a.push(b);return a.join("")},parse:function(a){var e=a.length,c=this._map,f=c.charAt(64);f&&(f=a.indexOf(f),-1!=f&&(e=f));for(var f=[],g=0,k=0;k<
e;k++)if(k%4){var i=c.indexOf(a.charAt(k-1))<<2*(k%4),l=c.indexOf(a.charAt(k))>>>6-2*(k%4);f[g>>>2]|=(i|l)<<24-8*(g%4);g++}return b.create(f,g)},_map:"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="}})();(function(){var a=CryptoJS,b=a.enc.Utf8;a.algo.HMAC=a.lib.Base.extend({init:function(a,e){a=this._hasher=new a.init;"string"==typeof e&&(e=b.parse(e));var c=a.blockSize,f=4*c;e.sigBytes>f&&(e=a.finalize(e));e.clamp();for(var g=this._oKey=e.clone(),k=this._iKey=e.clone(),i=g.words,l=k.words,h=0;h<c;h++)i[h]^=1549556828,l[h]^=909522486;g.sigBytes=k.sigBytes=f;this.reset()},reset:function(){var a=this._hasher;a.reset();a.update(this._iKey)},update:function(a){this._hasher.update(a);return this},finalize:function(a){var b=
this._hasher,a=b.finalize(a);b.reset();return b.finalize(this._oKey.clone().concat(a))}})})();(function(a){var b=CryptoJS,d=b.lib,e=d.WordArray,c=d.Hasher,d=b.algo,f=[],g=[];(function(){function c(b){for(var d=a.sqrt(b),e=2;e<=d;e++)if(!(b%e))return!1;return!0}function b(a){return 4294967296*(a-(a|0))|0}for(var d=2,e=0;64>e;)c(d)&&(8>e&&(f[e]=b(a.pow(d,0.5))),g[e]=b(a.pow(d,1/3)),e++),d++})();var k=[],d=d.SHA256=c.extend({_doReset:function(){this._hash=new e.init(f.slice(0))},_doProcessBlock:function(a,c){for(var b=this._hash.words,d=b[0],e=b[1],f=b[2],s=b[3],m=b[4],q=b[5],t=b[6],r=b[7],o=
0;64>o;o++){if(16>o)k[o]=a[c+o]|0;else{var v=k[o-15],u=k[o-2];k[o]=((v<<25|v>>>7)^(v<<14|v>>>18)^v>>>3)+k[o-7]+((u<<15|u>>>17)^(u<<13|u>>>19)^u>>>10)+k[o-16]}v=r+((m<<26|m>>>6)^(m<<21|m>>>11)^(m<<7|m>>>25))+(m&q^~m&t)+g[o]+k[o];u=((d<<30|d>>>2)^(d<<19|d>>>13)^(d<<10|d>>>22))+(d&e^d&f^e&f);r=t;t=q;q=m;m=s+v|0;s=f;f=e;e=d;d=v+u|0}b[0]=b[0]+d|0;b[1]=b[1]+e|0;b[2]=b[2]+f|0;b[3]=b[3]+s|0;b[4]=b[4]+m|0;b[5]=b[5]+q|0;b[6]=b[6]+t|0;b[7]=b[7]+r|0},_doFinalize:function(){var c=this._data,b=c.words,d=8*this._nDataBytes,
e=8*c.sigBytes;b[e>>>5]|=128<<24-e%32;b[(e+64>>>9<<4)+14]=a.floor(d/4294967296);b[(e+64>>>9<<4)+15]=d;c.sigBytes=4*b.length;this._process();return this._hash},clone:function(){var a=c.clone.call(this);a._hash=this._hash.clone();return a}});b.SHA256=c._createHelper(d);b.HmacSHA256=c._createHmacHelper(d)})(Math);(function(){var a=CryptoJS,b=a.lib,d=b.Base,e=b.WordArray,b=a.algo,c=b.HMAC,f=b.PBKDF2=d.extend({cfg:d.extend({keySize:4,hasher:b.SHA1,iterations:1}),init:function(a){this.cfg=this.cfg.extend(a)},compute:function(a,b){for(var d=this.cfg,f=c.create(d.hasher,a),h=e.create(),n=e.create([1]),j=h.words,p=n.words,s=d.keySize,d=d.iterations;j.length<s;){var m=f.update(b).finalize(n);f.reset();for(var q=m.words,t=q.length,r=m,o=1;o<d;o++){r=f.finalize(r);f.reset();for(var v=r.words,u=0;u<t;u++)q[u]^=v[u]}h.concat(m);
p[0]++}h.sigBytes=4*s;return h}});a.PBKDF2=function(a,c,b){return f.create(b).compute(a,c)}})();/*
 MIT License (c) 2011-2013 Copyright Tavendo GmbH. */
var AUTOBAHNJS_VERSION="0.7.6",AUTOBAHNJS_DEBUG=!1,ab=window.ab={};ab._version=AUTOBAHNJS_VERSION;
(function(){Array.prototype.indexOf||(Array.prototype.indexOf=function(a){if(null===this)throw new TypeError;var b=Object(this),d=b.length>>>0;if(0===d)return-1;var e=0;0<arguments.length&&(e=Number(arguments[1]),e!==e?e=0:0!==e&&Infinity!==e&&-Infinity!==e&&(e=(0<e||-1)*Math.floor(Math.abs(e))));if(e>=d)return-1;for(e=0<=e?e:Math.max(d-Math.abs(e),0);e<d;e++)if(e in b&&b[e]===a)return e;return-1});Array.prototype.forEach||(Array.prototype.forEach=function(a,b){var d,e;if(this===null)throw new TypeError(" this is null or not defined");
var c=Object(this),f=c.length>>>0;if({}.toString.call(a)!=="[object Function]")throw new TypeError(a+" is not a function");b&&(d=b);for(e=0;e<f;){var g;if(e in c){g=c[e];a.call(d,g,e,c)}e++}})})();ab._sliceUserAgent=function(a,b,d){var e=[],c=navigator.userAgent,a=c.indexOf(a),b=c.indexOf(b,a);0>b&&(b=c.length);d=c.slice(a,b).split(d);c=d[1].split(".");for(b=0;b<c.length;++b)e.push(parseInt(c[b],10));return{name:d[0],version:e}};
ab.getBrowser=function(){var a=navigator.userAgent;return-1<a.indexOf("Chrome")?ab._sliceUserAgent("Chrome"," ","/"):-1<a.indexOf("Safari")?ab._sliceUserAgent("Safari"," ","/"):-1<a.indexOf("Firefox")?ab._sliceUserAgent("Firefox"," ","/"):-1<a.indexOf("MSIE")?ab._sliceUserAgent("MSIE",";"," "):null};ab.browserNotSupportedMessage="Browser does not support WebSockets (RFC6455)";
ab.deriveKey=function(a,b){return b&&b.salt?CryptoJS.PBKDF2(a,b.salt,{keySize:(b.keylen||32)/4,iterations:b.iterations||1E4,hasher:CryptoJS.algo.SHA256}).toString(CryptoJS.enc.Base64):a};ab._idchars="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";ab._idlen=16;ab._subprotocol="wamp";ab._newid=function(){for(var a="",b=0;b<ab._idlen;b+=1)a+=ab._idchars.charAt(Math.floor(Math.random()*ab._idchars.length));return a};ab._newidFast=function(){return Math.random().toString(36)};
ab.log=function(){if(1<arguments.length){console.group("Log Item");for(var a=0;a<arguments.length;a+=1)console.log(arguments[a]);console.groupEnd()}else console.log(arguments[0])};ab._debugrpc=!1;ab._debugpubsub=!1;ab._debugws=!1;ab.debug=function(a,b){if("console"in window)ab._debugrpc=a,ab._debugpubsub=a,ab._debugws=b;else throw"browser does not support console object";};ab.version=function(){return ab._version};ab.PrefixMap=function(){this._index={};this._rindex={}};
ab.PrefixMap.prototype.get=function(a){return this._index[a]};ab.PrefixMap.prototype.set=function(a,b){this._index[a]=b;this._rindex[b]=a};ab.PrefixMap.prototype.setDefault=function(a){this._index[""]=a;this._rindex[a]=""};ab.PrefixMap.prototype.remove=function(a){var b=this._index[a];b&&(delete this._index[a],delete this._rindex[b])};
ab.PrefixMap.prototype.resolve=function(a,b){var d=a.indexOf(":");if(0<=d){var e=a.substring(0,d);if(this._index[e])return this._index[e]+a.substring(d+1)}return!0==b?a:null};ab.PrefixMap.prototype.shrink=function(a,b){for(var d=a.length;0<d;d-=1){var e=this._rindex[a.substring(0,d)];if(e)return e+":"+a.substring(d)}return!0==b?a:null};ab._MESSAGE_TYPEID_WELCOME=0;ab._MESSAGE_TYPEID_PREFIX=1;ab._MESSAGE_TYPEID_CALL=2;ab._MESSAGE_TYPEID_CALL_RESULT=3;ab._MESSAGE_TYPEID_CALL_ERROR=4;
ab._MESSAGE_TYPEID_SUBSCRIBE=5;ab._MESSAGE_TYPEID_UNSUBSCRIBE=6;ab._MESSAGE_TYPEID_PUBLISH=7;ab._MESSAGE_TYPEID_EVENT=8;ab.CONNECTION_CLOSED=0;ab.CONNECTION_LOST=1;ab.CONNECTION_RETRIES_EXCEEDED=2;ab.CONNECTION_UNREACHABLE=3;ab.CONNECTION_UNSUPPORTED=4;ab.CONNECTION_UNREACHABLE_SCHEDULED_RECONNECT=5;ab.CONNECTION_LOST_SCHEDULED_RECONNECT=6;ab._Deferred=when.defer;
ab._construct=function(a,b){return"WebSocket"in window?b?new WebSocket(a,b):new WebSocket(a):"MozWebSocket"in window?b?new MozWebSocket(a,b):new MozWebSocket(a):null};
ab.Session=function(a,b,d,e){var c=this;c._wsuri=a;c._options=e;c._websocket_onopen=b;c._websocket_onclose=d;c._websocket=null;c._websocket_connected=!1;c._session_id=null;c._wamp_version=null;c._server=null;c._calls={};c._subscriptions={};c._prefixes=new ab.PrefixMap;c._txcnt=0;c._rxcnt=0;c._websocket=c._options&&c._options.skipSubprotocolAnnounce?ab._construct(c._wsuri):ab._construct(c._wsuri,[ab._subprotocol]);if(!c._websocket){if(void 0!==d){d(ab.CONNECTION_UNSUPPORTED);return}throw ab.browserNotSupportedMessage;
}c._websocket.onmessage=function(a){ab._debugws&&(c._rxcnt+=1,console.group("WS Receive"),console.info(c._wsuri+"  ["+c._session_id+"]"),console.log(c._rxcnt),console.log(a.data),console.groupEnd());a=JSON.parse(a.data);if(a[1]in c._calls){if(a[0]===ab._MESSAGE_TYPEID_CALL_RESULT){var b=c._calls[a[1]],d=a[2];if(ab._debugrpc&&void 0!==b._ab_callobj){console.group("WAMP Call",b._ab_callobj[2]);console.timeEnd(b._ab_tid);console.group("Arguments");for(var e=3;e<b._ab_callobj.length;e+=1){var l=b._ab_callobj[e];
if(void 0!==l)console.log(l);else break}console.groupEnd();console.group("Result");console.log(d);console.groupEnd();console.groupEnd()}b.resolve(d)}else if(a[0]===ab._MESSAGE_TYPEID_CALL_ERROR){b=c._calls[a[1]];d=a[2];e=a[3];l=a[4];if(ab._debugrpc&&void 0!==b._ab_callobj){console.group("WAMP Call",b._ab_callobj[2]);console.timeEnd(b._ab_tid);console.group("Arguments");for(var h=3;h<b._ab_callobj.length;h+=1){var n=b._ab_callobj[h];if(void 0!==n)console.log(n);else break}console.groupEnd();console.group("Error");
console.log(d);console.log(e);void 0!==l&&console.log(l);console.groupEnd();console.groupEnd()}void 0!==l?b.reject({uri:d,desc:e,detail:l}):b.reject({uri:d,desc:e})}delete c._calls[a[1]]}else if(a[0]===ab._MESSAGE_TYPEID_EVENT){if(b=c._prefixes.resolve(a[1],!0),b in c._subscriptions){var j=a[1],p=a[2];ab._debugpubsub&&(console.group("WAMP Event"),console.info(c._wsuri+"  ["+c._session_id+"]"),console.log(j),console.log(p),console.groupEnd());c._subscriptions[b].forEach(function(a){a(j,p)})}}else if(a[0]===
ab._MESSAGE_TYPEID_WELCOME)if(null===c._session_id){c._session_id=a[1];c._wamp_version=a[2];c._server=a[3];if(ab._debugrpc||ab._debugpubsub)console.group("WAMP Welcome"),console.info(c._wsuri+"  ["+c._session_id+"]"),console.log(c._wamp_version),console.log(c._server),console.groupEnd();null!==c._websocket_onopen&&c._websocket_onopen()}else throw"protocol error (welcome message received more than once)";};c._websocket.onopen=function(){if(c._websocket.protocol!==ab._subprotocol)if("undefined"===typeof c._websocket.protocol)ab._debugws&&
(console.group("WS Warning"),console.info(c._wsuri),console.log("WebSocket object has no protocol attribute: WAMP subprotocol check skipped!"),console.groupEnd());else if(c._options&&c._options.skipSubprotocolCheck)ab._debugws&&(console.group("WS Warning"),console.info(c._wsuri),console.log("Server does not speak WAMP, but subprotocol check disabled by option!"),console.log(c._websocket.protocol),console.groupEnd());else throw c._websocket.close(1E3,"server does not speak WAMP"),"server does not speak WAMP (but '"+
c._websocket.protocol+"' !)";ab._debugws&&(console.group("WAMP Connect"),console.info(c._wsuri),console.log(c._websocket.protocol),console.groupEnd());c._websocket_connected=!0};c._websocket.onerror=function(){};c._websocket.onclose=function(a){ab._debugws&&(c._websocket_connected?console.log("Autobahn connection to "+c._wsuri+" lost (code "+a.code+", reason '"+a.reason+"', wasClean "+a.wasClean+")."):console.log("Autobahn could not connect to "+c._wsuri+" (code "+a.code+", reason '"+a.reason+"', wasClean "+
a.wasClean+")."));void 0!==c._websocket_onclose&&(c._websocket_connected?a.wasClean?c._websocket_onclose(ab.CONNECTION_CLOSED,"WS-"+a.code+": "+a.reason):c._websocket_onclose(ab.CONNECTION_LOST):c._websocket_onclose(ab.CONNECTION_UNREACHABLE));c._websocket_connected=!1;c._wsuri=null;c._websocket_onopen=null;c._websocket_onclose=null;c._websocket=null}};
ab.Session.prototype._send=function(a){if(!this._websocket_connected)throw"Autobahn not connected";switch(!0){case window.Prototype&&"undefined"===typeof top.window.__prototype_deleted:case "function"===typeof a.toJSON:a=a.toJSON();break;default:a=JSON.stringify(a)}this._websocket.send(a);this._txcnt+=1;ab._debugws&&(console.group("WS Send"),console.info(this._wsuri+"  ["+this._session_id+"]"),console.log(this._txcnt),console.log(a),console.groupEnd())};
ab.Session.prototype.close=function(){this._websocket_connected&&this._websocket.close()};ab.Session.prototype.sessionid=function(){return this._session_id};ab.Session.prototype.shrink=function(a,b){void 0===b&&(b=!0);return this._prefixes.shrink(a,b)};ab.Session.prototype.resolve=function(a,b){void 0===b&&(b=!0);return this._prefixes.resolve(a,b)};
ab.Session.prototype.prefix=function(a,b){this._prefixes.set(a,b);if(ab._debugrpc||ab._debugpubsub)console.group("WAMP Prefix"),console.info(this._wsuri+"  ["+this._session_id+"]"),console.log(a),console.log(b),console.groupEnd();this._send([ab._MESSAGE_TYPEID_PREFIX,a,b])};
ab.Session.prototype.call=function(){for(var a=new ab._Deferred,b;!(b=ab._newidFast(),!(b in this._calls)););this._calls[b]=a;for(var d=this._prefixes.shrink(arguments[0],!0),d=[ab._MESSAGE_TYPEID_CALL,b,d],e=1;e<arguments.length;e+=1)d.push(arguments[e]);this._send(d);ab._debugrpc&&(a._ab_callobj=d,a._ab_tid=this._wsuri+"  ["+this._session_id+"]["+b+"]",console.time(a._ab_tid),console.info());return a};
ab.Session.prototype.subscribe=function(a,b){var d=this._prefixes.resolve(a,!0);d in this._subscriptions||(ab._debugpubsub&&(console.group("WAMP Subscribe"),console.info(this._wsuri+"  ["+this._session_id+"]"),console.log(a),console.log(b),console.groupEnd()),this._send([ab._MESSAGE_TYPEID_SUBSCRIBE,a]),this._subscriptions[d]=[]);if(-1===this._subscriptions[d].indexOf(b))this._subscriptions[d].push(b);else throw"callback "+b+" already subscribed for topic "+d;};
ab.Session.prototype.unsubscribe=function(a,b){var d=this._prefixes.resolve(a,!0);if(d in this._subscriptions){var e;if(void 0!==b){var c=this._subscriptions[d].indexOf(b);if(-1!==c)e=b,this._subscriptions[d].splice(c,1);else throw"no callback "+b+" subscribed on topic "+d;}else e=this._subscriptions[d].slice(),this._subscriptions[d]=[];0===this._subscriptions[d].length&&(delete this._subscriptions[d],ab._debugpubsub&&(console.group("WAMP Unsubscribe"),console.info(this._wsuri+"  ["+this._session_id+
"]"),console.log(a),console.log(e),console.groupEnd()),this._send([ab._MESSAGE_TYPEID_UNSUBSCRIBE,a]))}else throw"not subscribed to topic "+d;};
ab.Session.prototype.publish=function(){var a=arguments[0],b=arguments[1],d=null,e=null,c=null,f=null;if(3<arguments.length){if(!(arguments[2]instanceof Array))throw"invalid argument type(s)";if(!(arguments[3]instanceof Array))throw"invalid argument type(s)";e=arguments[2];c=arguments[3];f=[ab._MESSAGE_TYPEID_PUBLISH,a,b,e,c]}else if(2<arguments.length)if("boolean"===typeof arguments[2])d=arguments[2],f=[ab._MESSAGE_TYPEID_PUBLISH,a,b,d];else if(arguments[2]instanceof Array)e=arguments[2],f=[ab._MESSAGE_TYPEID_PUBLISH,
a,b,e];else throw"invalid argument type(s)";else f=[ab._MESSAGE_TYPEID_PUBLISH,a,b];ab._debugpubsub&&(console.group("WAMP Publish"),console.info(this._wsuri+"  ["+this._session_id+"]"),console.log(a),console.log(b),null!==d?console.log(d):null!==e&&(console.log(e),null!==c&&console.log(c)),console.groupEnd());this._send(f)};ab.Session.prototype.authreq=function(a,b){return this.call("http://api.wamp.ws/procedure#authreq",a,b)};
ab.Session.prototype.authsign=function(a,b){b||(b="");return CryptoJS.HmacSHA256(a,b).toString(CryptoJS.enc.Base64)};ab.Session.prototype.auth=function(a){return this.call("http://api.wamp.ws/procedure#auth",a)};
ab._connect=function(a){var b=new ab.Session(a.wsuri,function(){a.connects+=1;a.retryCount=0;a.onConnect(b)},function(b,e){switch(b){case ab.CONNECTION_CLOSED:a.onHangup(b,"Connection was closed properly ["+e+"]");break;case ab.CONNECTION_UNSUPPORTED:a.onHangup(b,"Browser does not support WebSocket.");break;case ab.CONNECTION_UNREACHABLE:a.retryCount+=1;if(0==a.connects)a.onHangup(b,"Connection could not be established.");else if(a.retryCount<=a.options.maxRetries){var c=a.onHangup(ab.CONNECTION_UNREACHABLE_SCHEDULED_RECONNECT,
"Connection unreachable - scheduled reconnect to occur in "+a.options.retryDelay/1E3+" second(s).",{delay:a.options.retryDelay,retries:a.retryCount,maxretries:a.options.maxRetries});c?(console.log("Connection unreachable - retrying stopped by app"),a.onHangup(ab.CONNECTION_RETRIES_EXCEEDED,"Number of connection retries exceeded.")):(console.log("Connection unreachable - retrying ("+a.retryCount+") .."),window.setTimeout(ab._connect,a.options.retryDelay,a))}else a.onHangup(ab.CONNECTION_RETRIES_EXCEEDED,
"Number of connection retries exceeded.");break;case ab.CONNECTION_LOST:a.retryCount+=1;if(a.retryCount<=a.options.maxRetries)(c=a.onHangup(ab.CONNECTION_LOST_SCHEDULED_RECONNECT,"Connection lost - scheduled reconnect to occur in "+a.options.retryDelay/1E3+" second(s).",{delay:a.options.retryDelay,retries:a.retryCount,maxretries:a.options.maxRetries}))?(console.log("Connection lost - retrying stopped by app"),a.onHangup(ab.CONNECTION_RETRIES_EXCEEDED,"Connection lost.")):(console.log("Connection lost - retrying ("+
a.retryCount+") .."),window.setTimeout(ab._connect,a.options.retryDelay,a));else a.onHangup(ab.CONNECTION_RETRIES_EXCEEDED,"Connection lost.");break;default:throw"unhandled close code in ab._connect";}},a.options)};
ab.connect=function(a,b,d,e){var c={};c.wsuri=a;c.options=e?e:{};void 0==c.options.retryDelay&&(c.options.retryDelay=5E3);void 0==c.options.maxRetries&&(c.options.maxRetries=10);void 0==c.options.skipSubprotocolCheck&&(c.options.skipSubprotocolCheck=!1);void 0==c.options.skipSubprotocolAnnounce&&(c.options.skipSubprotocolAnnounce=!1);if(b)c.onConnect=b;else throw"onConnect handler required!";c.onHangup=d?d:function(a,b,c){console.log(a,b,c)};c.connects=0;c.retryCount=0;ab._connect(c)};ab._UA_FIREFOX=/.*Firefox\/([0-9+]*).*/;ab._UA_CHROME=/.*Chrome\/([0-9+]*).*/;ab._UA_CHROMEFRAME=/.*chromeframe\/([0-9]*).*/;ab._UA_WEBKIT=/.*AppleWebKit\/([0-9+.]*)w*.*/;ab._UA_WEBOS=/.*webOS\/([0-9+.]*)w*.*/;ab._matchRegex=function(a,b){var d=b.exec(a);return d?d[1]:d};
ab.lookupWsSupport=function(){var a=navigator.userAgent;if(-1<a.indexOf("MSIE")){if(-1<a.indexOf("MSIE 10"))return[!0,!0,!0];if(-1<a.indexOf("chromeframe")){var b=parseInt(ab._matchRegex(a,ab._UA_CHROMEFRAME));return 14<=b?[!0,!1,!0]:[!1,!1,!1]}if(-1<a.indexOf("MSIE 8")||-1<a.indexOf("MSIE 9"))return[!0,!0,!0]}else{if(-1<a.indexOf("Firefox")){if(b=parseInt(ab._matchRegex(a,ab._UA_FIREFOX))){if(7<=b)return[!0,!1,!0];if(3<=b)return[!0,!0,!0]}return[!1,!1,!0]}if(-1<a.indexOf("Safari")&&-1==a.indexOf("Chrome")){if(b=
ab._matchRegex(a,ab._UA_WEBKIT))return-1<a.indexOf("Windows")&&"534+"==b||-1<a.indexOf("Macintosh")&&(b=b.replace("+","").split("."),535==parseInt(b[0])&&24<=parseInt(b[1])||535<parseInt(b[0]))?[!0,!1,!0]:-1<a.indexOf("webOS")?(b=ab._matchRegex(a,ab._UA_WEBOS).split("."),2==parseInt(b[0])?[!1,!0,!0]:[!1,!1,!1]):[!0,!0,!0]}else if(-1<a.indexOf("Chrome")){if(b=parseInt(ab._matchRegex(a,ab._UA_CHROME)))return 14<=b?[!0,!1,!0]:4<=b?[!0,!0,!0]:[!1,!1,!0]}else if(-1<a.indexOf("Android")){if(-1<a.indexOf("Firefox")||
-1<a.indexOf("CrMo"))return[!0,!1,!0];if(-1<a.indexOf("Opera"))return[!1,!1,!0];if(-1<a.indexOf("CrMo"))return[!0,!0,!0]}else if(-1<a.indexOf("iPhone")||-1<a.indexOf("iPad")||-1<a.indexOf("iPod"))return[!1,!1,!0]}return[!1,!1,!1]};
// Underscore.js 1.4.4
// ===================

// > http://underscorejs.org
// > (c) 2009-2013 Jeremy Ashkenas, DocumentCloud Inc.
// > Underscore may be freely distributed under the MIT license.

// Baseline setup
// --------------
(function() {

  // Establish the root object, `window` in the browser, or `global` on the server.
  var root = this;

  // Save the previous value of the `_` variable.
  var previousUnderscore = root._;

  // Establish the object that gets returned to break out of a loop iteration.
  var breaker = {};

  // Save bytes in the minified (but not gzipped) version:
  var ArrayProto = Array.prototype, ObjProto = Object.prototype, FuncProto = Function.prototype;

  // Create quick reference variables for speed access to core prototypes.
  var push             = ArrayProto.push,
      slice            = ArrayProto.slice,
      concat           = ArrayProto.concat,
      toString         = ObjProto.toString,
      hasOwnProperty   = ObjProto.hasOwnProperty;

  // All **ECMAScript 5** native function implementations that we hope to use
  // are declared here.
  var
    nativeForEach      = ArrayProto.forEach,
    nativeMap          = ArrayProto.map,
    nativeReduce       = ArrayProto.reduce,
    nativeReduceRight  = ArrayProto.reduceRight,
    nativeFilter       = ArrayProto.filter,
    nativeEvery        = ArrayProto.every,
    nativeSome         = ArrayProto.some,
    nativeIndexOf      = ArrayProto.indexOf,
    nativeLastIndexOf  = ArrayProto.lastIndexOf,
    nativeIsArray      = Array.isArray,
    nativeKeys         = Object.keys,
    nativeBind         = FuncProto.bind;

  // Create a safe reference to the Underscore object for use below.
  var _ = function(obj) {
    if (obj instanceof _) return obj;
    if (!(this instanceof _)) return new _(obj);
    this._wrapped = obj;
  };

  // Export the Underscore object for **Node.js**, with
  // backwards-compatibility for the old `require()` API. If we're in
  // the browser, add `_` as a global object via a string identifier,
  // for Closure Compiler "advanced" mode.
  if (typeof exports !== 'undefined') {
    if (typeof module !== 'undefined' && module.exports) {
      exports = module.exports = _;
    }
    exports._ = _;
  } else {
    root._ = _;
  }

  // Current version.
  _.VERSION = '1.4.4';

  // Collection Functions
  // --------------------

  // The cornerstone, an `each` implementation, aka `forEach`.
  // Handles objects with the built-in `forEach`, arrays, and raw objects.
  // Delegates to **ECMAScript 5**'s native `forEach` if available.
  var each = _.each = _.forEach = function(obj, iterator, context) {
    if (obj == null) return;
    if (nativeForEach && obj.forEach === nativeForEach) {
      obj.forEach(iterator, context);
    } else if (obj.length === +obj.length) {
      for (var i = 0, l = obj.length; i < l; i++) {
        if (iterator.call(context, obj[i], i, obj) === breaker) return;
      }
    } else {
      for (var key in obj) {
        if (_.has(obj, key)) {
          if (iterator.call(context, obj[key], key, obj) === breaker) return;
        }
      }
    }
  };

  // Return the results of applying the iterator to each element.
  // Delegates to **ECMAScript 5**'s native `map` if available.
  _.map = _.collect = function(obj, iterator, context) {
    var results = [];
    if (obj == null) return results;
    if (nativeMap && obj.map === nativeMap) return obj.map(iterator, context);
    each(obj, function(value, index, list) {
      results[results.length] = iterator.call(context, value, index, list);
    });
    return results;
  };

  var reduceError = 'Reduce of empty array with no initial value';

  // **Reduce** builds up a single result from a list of values, aka `inject`,
  // or `foldl`. Delegates to **ECMAScript 5**'s native `reduce` if available.
  _.reduce = _.foldl = _.inject = function(obj, iterator, memo, context) {
    var initial = arguments.length > 2;
    if (obj == null) obj = [];
    if (nativeReduce && obj.reduce === nativeReduce) {
      if (context) iterator = _.bind(iterator, context);
      return initial ? obj.reduce(iterator, memo) : obj.reduce(iterator);
    }
    each(obj, function(value, index, list) {
      if (!initial) {
        memo = value;
        initial = true;
      } else {
        memo = iterator.call(context, memo, value, index, list);
      }
    });
    if (!initial) throw new TypeError(reduceError);
    return memo;
  };

  // The right-associative version of reduce, also known as `foldr`.
  // Delegates to **ECMAScript 5**'s native `reduceRight` if available.
  _.reduceRight = _.foldr = function(obj, iterator, memo, context) {
    var initial = arguments.length > 2;
    if (obj == null) obj = [];
    if (nativeReduceRight && obj.reduceRight === nativeReduceRight) {
      if (context) iterator = _.bind(iterator, context);
      return initial ? obj.reduceRight(iterator, memo) : obj.reduceRight(iterator);
    }
    var length = obj.length;
    if (length !== +length) {
      var keys = _.keys(obj);
      length = keys.length;
    }
    each(obj, function(value, index, list) {
      index = keys ? keys[--length] : --length;
      if (!initial) {
        memo = obj[index];
        initial = true;
      } else {
        memo = iterator.call(context, memo, obj[index], index, list);
      }
    });
    if (!initial) throw new TypeError(reduceError);
    return memo;
  };

  // Return the first value which passes a truth test. Aliased as `detect`.
  _.find = _.detect = function(obj, iterator, context) {
    var result;
    any(obj, function(value, index, list) {
      if (iterator.call(context, value, index, list)) {
        result = value;
        return true;
      }
    });
    return result;
  };

  // Return all the elements that pass a truth test.
  // Delegates to **ECMAScript 5**'s native `filter` if available.
  // Aliased as `select`.
  _.filter = _.select = function(obj, iterator, context) {
    var results = [];
    if (obj == null) return results;
    if (nativeFilter && obj.filter === nativeFilter) return obj.filter(iterator, context);
    each(obj, function(value, index, list) {
      if (iterator.call(context, value, index, list)) results[results.length] = value;
    });
    return results;
  };

  // Return all the elements for which a truth test fails.
  _.reject = function(obj, iterator, context) {
    return _.filter(obj, function(value, index, list) {
      return !iterator.call(context, value, index, list);
    }, context);
  };

  // Determine whether all of the elements match a truth test.
  // Delegates to **ECMAScript 5**'s native `every` if available.
  // Aliased as `all`.
  _.every = _.all = function(obj, iterator, context) {
    iterator || (iterator = _.identity);
    var result = true;
    if (obj == null) return result;
    if (nativeEvery && obj.every === nativeEvery) return obj.every(iterator, context);
    each(obj, function(value, index, list) {
      if (!(result = result && iterator.call(context, value, index, list))) return breaker;
    });
    return !!result;
  };

  // Determine if at least one element in the object matches a truth test.
  // Delegates to **ECMAScript 5**'s native `some` if available.
  // Aliased as `any`.
  var any = _.some = _.any = function(obj, iterator, context) {
    iterator || (iterator = _.identity);
    var result = false;
    if (obj == null) return result;
    if (nativeSome && obj.some === nativeSome) return obj.some(iterator, context);
    each(obj, function(value, index, list) {
      if (result || (result = iterator.call(context, value, index, list))) return breaker;
    });
    return !!result;
  };

  // Determine if the array or object contains a given value (using `===`).
  // Aliased as `include`.
  _.contains = _.include = function(obj, target) {
    if (obj == null) return false;
    if (nativeIndexOf && obj.indexOf === nativeIndexOf) return obj.indexOf(target) != -1;
    return any(obj, function(value) {
      return value === target;
    });
  };

  // Invoke a method (with arguments) on every item in a collection.
  _.invoke = function(obj, method) {
    var args = slice.call(arguments, 2);
    var isFunc = _.isFunction(method);
    return _.map(obj, function(value) {
      return (isFunc ? method : value[method]).apply(value, args);
    });
  };

  // Convenience version of a common use case of `map`: fetching a property.
  _.pluck = function(obj, key) {
    return _.map(obj, function(value){ return value[key]; });
  };

  // Convenience version of a common use case of `filter`: selecting only objects
  // containing specific `key:value` pairs.
  _.where = function(obj, attrs, first) {
    if (_.isEmpty(attrs)) return first ? null : [];
    return _[first ? 'find' : 'filter'](obj, function(value) {
      for (var key in attrs) {
        if (attrs[key] !== value[key]) return false;
      }
      return true;
    });
  };

  // Convenience version of a common use case of `find`: getting the first object
  // containing specific `key:value` pairs.
  _.findWhere = function(obj, attrs) {
    return _.where(obj, attrs, true);
  };

  // Return the maximum element or (element-based computation).
  // Can't optimize arrays of integers longer than 65,535 elements.
  // See: https://bugs.webkit.org/show_bug.cgi?id=80797
  _.max = function(obj, iterator, context) {
    if (!iterator && _.isArray(obj) && obj[0] === +obj[0] && obj.length < 65535) {
      return Math.max.apply(Math, obj);
    }
    if (!iterator && _.isEmpty(obj)) return -Infinity;
    var result = {computed : -Infinity, value: -Infinity};
    each(obj, function(value, index, list) {
      var computed = iterator ? iterator.call(context, value, index, list) : value;
      computed >= result.computed && (result = {value : value, computed : computed});
    });
    return result.value;
  };

  // Return the minimum element (or element-based computation).
  _.min = function(obj, iterator, context) {
    if (!iterator && _.isArray(obj) && obj[0] === +obj[0] && obj.length < 65535) {
      return Math.min.apply(Math, obj);
    }
    if (!iterator && _.isEmpty(obj)) return Infinity;
    var result = {computed : Infinity, value: Infinity};
    each(obj, function(value, index, list) {
      var computed = iterator ? iterator.call(context, value, index, list) : value;
      computed < result.computed && (result = {value : value, computed : computed});
    });
    return result.value;
  };

  // Shuffle an array.
  _.shuffle = function(obj) {
    var rand;
    var index = 0;
    var shuffled = [];
    each(obj, function(value) {
      rand = _.random(index++);
      shuffled[index - 1] = shuffled[rand];
      shuffled[rand] = value;
    });
    return shuffled;
  };

  // An internal function to generate lookup iterators.
  var lookupIterator = function(value) {
    return _.isFunction(value) ? value : function(obj){ return obj[value]; };
  };

  // Sort the object's values by a criterion produced by an iterator.
  _.sortBy = function(obj, value, context) {
    var iterator = lookupIterator(value);
    return _.pluck(_.map(obj, function(value, index, list) {
      return {
        value : value,
        index : index,
        criteria : iterator.call(context, value, index, list)
      };
    }).sort(function(left, right) {
      var a = left.criteria;
      var b = right.criteria;
      if (a !== b) {
        if (a > b || a === void 0) return 1;
        if (a < b || b === void 0) return -1;
      }
      return left.index < right.index ? -1 : 1;
    }), 'value');
  };

  // An internal function used for aggregate "group by" operations.
  var group = function(obj, value, context, behavior) {
    var result = {};
    var iterator = lookupIterator(value || _.identity);
    each(obj, function(value, index) {
      var key = iterator.call(context, value, index, obj);
      behavior(result, key, value);
    });
    return result;
  };

  // Groups the object's values by a criterion. Pass either a string attribute
  // to group by, or a function that returns the criterion.
  _.groupBy = function(obj, value, context) {
    return group(obj, value, context, function(result, key, value) {
      (_.has(result, key) ? result[key] : (result[key] = [])).push(value);
    });
  };

  // Counts instances of an object that group by a certain criterion. Pass
  // either a string attribute to count by, or a function that returns the
  // criterion.
  _.countBy = function(obj, value, context) {
    return group(obj, value, context, function(result, key) {
      if (!_.has(result, key)) result[key] = 0;
      result[key]++;
    });
  };

  // Use a comparator function to figure out the smallest index at which
  // an object should be inserted so as to maintain order. Uses binary search.
  _.sortedIndex = function(array, obj, iterator, context) {
    iterator = iterator == null ? _.identity : lookupIterator(iterator);
    var value = iterator.call(context, obj);
    var low = 0, high = array.length;
    while (low < high) {
      var mid = (low + high) >>> 1;
      iterator.call(context, array[mid]) < value ? low = mid + 1 : high = mid;
    }
    return low;
  };

  // Safely convert anything iterable into a real, live array.
  _.toArray = function(obj) {
    if (!obj) return [];
    if (_.isArray(obj)) return slice.call(obj);
    if (obj.length === +obj.length) return _.map(obj, _.identity);
    return _.values(obj);
  };

  // Return the number of elements in an object.
  _.size = function(obj) {
    if (obj == null) return 0;
    return (obj.length === +obj.length) ? obj.length : _.keys(obj).length;
  };

  // Array Functions
  // ---------------

  // Get the first element of an array. Passing **n** will return the first N
  // values in the array. Aliased as `head` and `take`. The **guard** check
  // allows it to work with `_.map`.
  _.first = _.head = _.take = function(array, n, guard) {
    if (array == null) return void 0;
    return (n != null) && !guard ? slice.call(array, 0, n) : array[0];
  };

  // Returns everything but the last entry of the array. Especially useful on
  // the arguments object. Passing **n** will return all the values in
  // the array, excluding the last N. The **guard** check allows it to work with
  // `_.map`.
  _.initial = function(array, n, guard) {
    return slice.call(array, 0, array.length - ((n == null) || guard ? 1 : n));
  };

  // Get the last element of an array. Passing **n** will return the last N
  // values in the array. The **guard** check allows it to work with `_.map`.
  _.last = function(array, n, guard) {
    if (array == null) return void 0;
    if ((n != null) && !guard) {
      return slice.call(array, Math.max(array.length - n, 0));
    } else {
      return array[array.length - 1];
    }
  };

  // Returns everything but the first entry of the array. Aliased as `tail` and `drop`.
  // Especially useful on the arguments object. Passing an **n** will return
  // the rest N values in the array. The **guard**
  // check allows it to work with `_.map`.
  _.rest = _.tail = _.drop = function(array, n, guard) {
    return slice.call(array, (n == null) || guard ? 1 : n);
  };

  // Trim out all falsy values from an array.
  _.compact = function(array) {
    return _.filter(array, _.identity);
  };

  // Internal implementation of a recursive `flatten` function.
  var flatten = function(input, shallow, output) {
    each(input, function(value) {
      if (_.isArray(value)) {
        shallow ? push.apply(output, value) : flatten(value, shallow, output);
      } else {
        output.push(value);
      }
    });
    return output;
  };

  // Return a completely flattened version of an array.
  _.flatten = function(array, shallow) {
    return flatten(array, shallow, []);
  };

  // Return a version of the array that does not contain the specified value(s).
  _.without = function(array) {
    return _.difference(array, slice.call(arguments, 1));
  };

  // Produce a duplicate-free version of the array. If the array has already
  // been sorted, you have the option of using a faster algorithm.
  // Aliased as `unique`.
  _.uniq = _.unique = function(array, isSorted, iterator, context) {
    if (_.isFunction(isSorted)) {
      context = iterator;
      iterator = isSorted;
      isSorted = false;
    }
    var initial = iterator ? _.map(array, iterator, context) : array;
    var results = [];
    var seen = [];
    each(initial, function(value, index) {
      if (isSorted ? (!index || seen[seen.length - 1] !== value) : !_.contains(seen, value)) {
        seen.push(value);
        results.push(array[index]);
      }
    });
    return results;
  };

  // Produce an array that contains the union: each distinct element from all of
  // the passed-in arrays.
  _.union = function() {
    return _.uniq(concat.apply(ArrayProto, arguments));
  };

  // Produce an array that contains every item shared between all the
  // passed-in arrays.
  _.intersection = function(array) {
    var rest = slice.call(arguments, 1);
    return _.filter(_.uniq(array), function(item) {
      return _.every(rest, function(other) {
        return _.indexOf(other, item) >= 0;
      });
    });
  };

  // Take the difference between one array and a number of other arrays.
  // Only the elements present in just the first array will remain.
  _.difference = function(array) {
    var rest = concat.apply(ArrayProto, slice.call(arguments, 1));
    return _.filter(array, function(value){ return !_.contains(rest, value); });
  };

  // Zip together multiple lists into a single array -- elements that share
  // an index go together.
  _.zip = function() {
    var args = slice.call(arguments);
    var length = _.max(_.pluck(args, 'length'));
    var results = new Array(length);
    for (var i = 0; i < length; i++) {
      results[i] = _.pluck(args, "" + i);
    }
    return results;
  };

  // Converts lists into objects. Pass either a single array of `[key, value]`
  // pairs, or two parallel arrays of the same length -- one of keys, and one of
  // the corresponding values.
  _.object = function(list, values) {
    if (list == null) return {};
    var result = {};
    for (var i = 0, l = list.length; i < l; i++) {
      if (values) {
        result[list[i]] = values[i];
      } else {
        result[list[i][0]] = list[i][1];
      }
    }
    return result;
  };

  // If the browser doesn't supply us with indexOf (I'm looking at you, **MSIE**),
  // we need this function. Return the position of the first occurrence of an
  // item in an array, or -1 if the item is not included in the array.
  // Delegates to **ECMAScript 5**'s native `indexOf` if available.
  // If the array is large and already in sort order, pass `true`
  // for **isSorted** to use binary search.
  _.indexOf = function(array, item, isSorted) {
    if (array == null) return -1;
    var i = 0, l = array.length;
    if (isSorted) {
      if (typeof isSorted == 'number') {
        i = (isSorted < 0 ? Math.max(0, l + isSorted) : isSorted);
      } else {
        i = _.sortedIndex(array, item);
        return array[i] === item ? i : -1;
      }
    }
    if (nativeIndexOf && array.indexOf === nativeIndexOf) return array.indexOf(item, isSorted);
    for (; i < l; i++) if (array[i] === item) return i;
    return -1;
  };

  // Delegates to **ECMAScript 5**'s native `lastIndexOf` if available.
  _.lastIndexOf = function(array, item, from) {
    if (array == null) return -1;
    var hasIndex = from != null;
    if (nativeLastIndexOf && array.lastIndexOf === nativeLastIndexOf) {
      return hasIndex ? array.lastIndexOf(item, from) : array.lastIndexOf(item);
    }
    var i = (hasIndex ? from : array.length);
    while (i--) if (array[i] === item) return i;
    return -1;
  };

  // Generate an integer Array containing an arithmetic progression. A port of
  // the native Python `range()` function. See
  // [the Python documentation](http://docs.python.org/library/functions.html#range).
  _.range = function(start, stop, step) {
    if (arguments.length <= 1) {
      stop = start || 0;
      start = 0;
    }
    step = arguments[2] || 1;

    var len = Math.max(Math.ceil((stop - start) / step), 0);
    var idx = 0;
    var range = new Array(len);

    while(idx < len) {
      range[idx++] = start;
      start += step;
    }

    return range;
  };

  // Function (ahem) Functions
  // ------------------

  // Create a function bound to a given object (assigning `this`, and arguments,
  // optionally). Delegates to **ECMAScript 5**'s native `Function.bind` if
  // available.
  _.bind = function(func, context) {
    if (func.bind === nativeBind && nativeBind) return nativeBind.apply(func, slice.call(arguments, 1));
    var args = slice.call(arguments, 2);
    return function() {
      return func.apply(context, args.concat(slice.call(arguments)));
    };
  };

  // Partially apply a function by creating a version that has had some of its
  // arguments pre-filled, without changing its dynamic `this` context.
  _.partial = function(func) {
    var args = slice.call(arguments, 1);
    return function() {
      return func.apply(this, args.concat(slice.call(arguments)));
    };
  };

  // Bind all of an object's methods to that object. Useful for ensuring that
  // all callbacks defined on an object belong to it.
  _.bindAll = function(obj) {
    var funcs = slice.call(arguments, 1);
    if (funcs.length === 0) funcs = _.functions(obj);
    each(funcs, function(f) { obj[f] = _.bind(obj[f], obj); });
    return obj;
  };

  // Memoize an expensive function by storing its results.
  _.memoize = function(func, hasher) {
    var memo = {};
    hasher || (hasher = _.identity);
    return function() {
      var key = hasher.apply(this, arguments);
      return _.has(memo, key) ? memo[key] : (memo[key] = func.apply(this, arguments));
    };
  };

  // Delays a function for the given number of milliseconds, and then calls
  // it with the arguments supplied.
  _.delay = function(func, wait) {
    var args = slice.call(arguments, 2);
    return setTimeout(function(){ return func.apply(null, args); }, wait);
  };

  // Defers a function, scheduling it to run after the current call stack has
  // cleared.
  _.defer = function(func) {
    return _.delay.apply(_, [func, 1].concat(slice.call(arguments, 1)));
  };

  // Returns a function, that, when invoked, will only be triggered at most once
  // during a given window of time.
  _.throttle = function(func, wait) {
    var context, args, timeout, result;
    var previous = 0;
    var later = function() {
      previous = new Date;
      timeout = null;
      result = func.apply(context, args);
    };
    return function() {
      var now = new Date;
      var remaining = wait - (now - previous);
      context = this;
      args = arguments;
      if (remaining <= 0) {
        clearTimeout(timeout);
        timeout = null;
        previous = now;
        result = func.apply(context, args);
      } else if (!timeout) {
        timeout = setTimeout(later, remaining);
      }
      return result;
    };
  };

  // Returns a function, that, as long as it continues to be invoked, will not
  // be triggered. The function will be called after it stops being called for
  // N milliseconds. If `immediate` is passed, trigger the function on the
  // leading edge, instead of the trailing.
  _.debounce = function(func, wait, immediate) {
    var timeout, result;
    return function() {
      var context = this, args = arguments;
      var later = function() {
        timeout = null;
        if (!immediate) result = func.apply(context, args);
      };
      var callNow = immediate && !timeout;
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
      if (callNow) result = func.apply(context, args);
      return result;
    };
  };

  // Returns a function that will be executed at most one time, no matter how
  // often you call it. Useful for lazy initialization.
  _.once = function(func) {
    var ran = false, memo;
    return function() {
      if (ran) return memo;
      ran = true;
      memo = func.apply(this, arguments);
      func = null;
      return memo;
    };
  };

  // Returns the first function passed as an argument to the second,
  // allowing you to adjust arguments, run code before and after, and
  // conditionally execute the original function.
  _.wrap = function(func, wrapper) {
    return function() {
      var args = [func];
      push.apply(args, arguments);
      return wrapper.apply(this, args);
    };
  };

  // Returns a function that is the composition of a list of functions, each
  // consuming the return value of the function that follows.
  _.compose = function() {
    var funcs = arguments;
    return function() {
      var args = arguments;
      for (var i = funcs.length - 1; i >= 0; i--) {
        args = [funcs[i].apply(this, args)];
      }
      return args[0];
    };
  };

  // Returns a function that will only be executed after being called N times.
  _.after = function(times, func) {
    if (times <= 0) return func();
    return function() {
      if (--times < 1) {
        return func.apply(this, arguments);
      }
    };
  };

  // Object Functions
  // ----------------

  // Retrieve the names of an object's properties.
  // Delegates to **ECMAScript 5**'s native `Object.keys`
  _.keys = nativeKeys || function(obj) {
    if (obj !== Object(obj)) throw new TypeError('Invalid object');
    var keys = [];
    for (var key in obj) if (_.has(obj, key)) keys[keys.length] = key;
    return keys;
  };

  // Retrieve the values of an object's properties.
  _.values = function(obj) {
    var values = [];
    for (var key in obj) if (_.has(obj, key)) values.push(obj[key]);
    return values;
  };

  // Convert an object into a list of `[key, value]` pairs.
  _.pairs = function(obj) {
    var pairs = [];
    for (var key in obj) if (_.has(obj, key)) pairs.push([key, obj[key]]);
    return pairs;
  };

  // Invert the keys and values of an object. The values must be serializable.
  _.invert = function(obj) {
    var result = {};
    for (var key in obj) if (_.has(obj, key)) result[obj[key]] = key;
    return result;
  };

  // Return a sorted list of the function names available on the object.
  // Aliased as `methods`
  _.functions = _.methods = function(obj) {
    var names = [];
    for (var key in obj) {
      if (_.isFunction(obj[key])) names.push(key);
    }
    return names.sort();
  };

  // Extend a given object with all the properties in passed-in object(s).
  _.extend = function(obj) {
    each(slice.call(arguments, 1), function(source) {
      if (source) {
        for (var prop in source) {
          obj[prop] = source[prop];
        }
      }
    });
    return obj;
  };

  // Return a copy of the object only containing the whitelisted properties.
  _.pick = function(obj) {
    var copy = {};
    var keys = concat.apply(ArrayProto, slice.call(arguments, 1));
    each(keys, function(key) {
      if (key in obj) copy[key] = obj[key];
    });
    return copy;
  };

   // Return a copy of the object without the blacklisted properties.
  _.omit = function(obj) {
    var copy = {};
    var keys = concat.apply(ArrayProto, slice.call(arguments, 1));
    for (var key in obj) {
      if (!_.contains(keys, key)) copy[key] = obj[key];
    }
    return copy;
  };

  // Fill in a given object with default properties.
  _.defaults = function(obj) {
    each(slice.call(arguments, 1), function(source) {
      if (source) {
        for (var prop in source) {
          if (obj[prop] == null) obj[prop] = source[prop];
        }
      }
    });
    return obj;
  };

  // Create a (shallow-cloned) duplicate of an object.
  _.clone = function(obj) {
    if (!_.isObject(obj)) return obj;
    return _.isArray(obj) ? obj.slice() : _.extend({}, obj);
  };

  // Invokes interceptor with the obj, and then returns obj.
  // The primary purpose of this method is to "tap into" a method chain, in
  // order to perform operations on intermediate results within the chain.
  _.tap = function(obj, interceptor) {
    interceptor(obj);
    return obj;
  };

  // Internal recursive comparison function for `isEqual`.
  var eq = function(a, b, aStack, bStack) {
    // Identical objects are equal. `0 === -0`, but they aren't identical.
    // See the Harmony `egal` proposal: http://wiki.ecmascript.org/doku.php?id=harmony:egal.
    if (a === b) return a !== 0 || 1 / a == 1 / b;
    // A strict comparison is necessary because `null == undefined`.
    if (a == null || b == null) return a === b;
    // Unwrap any wrapped objects.
    if (a instanceof _) a = a._wrapped;
    if (b instanceof _) b = b._wrapped;
    // Compare `[[Class]]` names.
    var className = toString.call(a);
    if (className != toString.call(b)) return false;
    switch (className) {
      // Strings, numbers, dates, and booleans are compared by value.
      case '[object String]':
        // Primitives and their corresponding object wrappers are equivalent; thus, `"5"` is
        // equivalent to `new String("5")`.
        return a == String(b);
      case '[object Number]':
        // `NaN`s are equivalent, but non-reflexive. An `egal` comparison is performed for
        // other numeric values.
        return a != +a ? b != +b : (a == 0 ? 1 / a == 1 / b : a == +b);
      case '[object Date]':
      case '[object Boolean]':
        // Coerce dates and booleans to numeric primitive values. Dates are compared by their
        // millisecond representations. Note that invalid dates with millisecond representations
        // of `NaN` are not equivalent.
        return +a == +b;
      // RegExps are compared by their source patterns and flags.
      case '[object RegExp]':
        return a.source == b.source &&
               a.global == b.global &&
               a.multiline == b.multiline &&
               a.ignoreCase == b.ignoreCase;
    }
    if (typeof a != 'object' || typeof b != 'object') return false;
    // Assume equality for cyclic structures. The algorithm for detecting cyclic
    // structures is adapted from ES 5.1 section 15.12.3, abstract operation `JO`.
    var length = aStack.length;
    while (length--) {
      // Linear search. Performance is inversely proportional to the number of
      // unique nested structures.
      if (aStack[length] == a) return bStack[length] == b;
    }
    // Add the first object to the stack of traversed objects.
    aStack.push(a);
    bStack.push(b);
    var size = 0, result = true;
    // Recursively compare objects and arrays.
    if (className == '[object Array]') {
      // Compare array lengths to determine if a deep comparison is necessary.
      size = a.length;
      result = size == b.length;
      if (result) {
        // Deep compare the contents, ignoring non-numeric properties.
        while (size--) {
          if (!(result = eq(a[size], b[size], aStack, bStack))) break;
        }
      }
    } else {
      // Objects with different constructors are not equivalent, but `Object`s
      // from different frames are.
      var aCtor = a.constructor, bCtor = b.constructor;
      if (aCtor !== bCtor && !(_.isFunction(aCtor) && (aCtor instanceof aCtor) &&
                               _.isFunction(bCtor) && (bCtor instanceof bCtor))) {
        return false;
      }
      // Deep compare objects.
      for (var key in a) {
        if (_.has(a, key)) {
          // Count the expected number of properties.
          size++;
          // Deep compare each member.
          if (!(result = _.has(b, key) && eq(a[key], b[key], aStack, bStack))) break;
        }
      }
      // Ensure that both objects contain the same number of properties.
      if (result) {
        for (key in b) {
          if (_.has(b, key) && !(size--)) break;
        }
        result = !size;
      }
    }
    // Remove the first object from the stack of traversed objects.
    aStack.pop();
    bStack.pop();
    return result;
  };

  // Perform a deep comparison to check if two objects are equal.
  _.isEqual = function(a, b) {
    return eq(a, b, [], []);
  };

  // Is a given array, string, or object empty?
  // An "empty" object has no enumerable own-properties.
  _.isEmpty = function(obj) {
    if (obj == null) return true;
    if (_.isArray(obj) || _.isString(obj)) return obj.length === 0;
    for (var key in obj) if (_.has(obj, key)) return false;
    return true;
  };

  // Is a given value a DOM element?
  _.isElement = function(obj) {
    return !!(obj && obj.nodeType === 1);
  };

  // Is a given value an array?
  // Delegates to ECMA5's native Array.isArray
  _.isArray = nativeIsArray || function(obj) {
    return toString.call(obj) == '[object Array]';
  };

  // Is a given variable an object?
  _.isObject = function(obj) {
    return obj === Object(obj);
  };

  // Add some isType methods: isArguments, isFunction, isString, isNumber, isDate, isRegExp.
  each(['Arguments', 'Function', 'String', 'Number', 'Date', 'RegExp'], function(name) {
    _['is' + name] = function(obj) {
      return toString.call(obj) == '[object ' + name + ']';
    };
  });

  // Define a fallback version of the method in browsers (ahem, IE), where
  // there isn't any inspectable "Arguments" type.
  if (!_.isArguments(arguments)) {
    _.isArguments = function(obj) {
      return !!(obj && _.has(obj, 'callee'));
    };
  }

  // Optimize `isFunction` if appropriate.
  if (typeof (/./) !== 'function') {
    _.isFunction = function(obj) {
      return typeof obj === 'function';
    };
  }

  // Is a given object a finite number?
  _.isFinite = function(obj) {
    return isFinite(obj) && !isNaN(parseFloat(obj));
  };

  // Is the given value `NaN`? (NaN is the only number which does not equal itself).
  _.isNaN = function(obj) {
    return _.isNumber(obj) && obj != +obj;
  };

  // Is a given value a boolean?
  _.isBoolean = function(obj) {
    return obj === true || obj === false || toString.call(obj) == '[object Boolean]';
  };

  // Is a given value equal to null?
  _.isNull = function(obj) {
    return obj === null;
  };

  // Is a given variable undefined?
  _.isUndefined = function(obj) {
    return obj === void 0;
  };

  // Shortcut function for checking if an object has a given property directly
  // on itself (in other words, not on a prototype).
  _.has = function(obj, key) {
    return hasOwnProperty.call(obj, key);
  };

  // Utility Functions
  // -----------------

  // Run Underscore.js in *noConflict* mode, returning the `_` variable to its
  // previous owner. Returns a reference to the Underscore object.
  _.noConflict = function() {
    root._ = previousUnderscore;
    return this;
  };

  // Keep the identity function around for default iterators.
  _.identity = function(value) {
    return value;
  };

  // Run a function **n** times.
  _.times = function(n, iterator, context) {
    var accum = Array(n);
    for (var i = 0; i < n; i++) accum[i] = iterator.call(context, i);
    return accum;
  };

  // Return a random integer between min and max (inclusive).
  _.random = function(min, max) {
    if (max == null) {
      max = min;
      min = 0;
    }
    return min + Math.floor(Math.random() * (max - min + 1));
  };

  // List of HTML entities for escaping.
  var entityMap = {
    escape: {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#x27;',
      '/': '&#x2F;'
    }
  };
  entityMap.unescape = _.invert(entityMap.escape);

  // Regexes containing the keys and values listed immediately above.
  var entityRegexes = {
    escape:   new RegExp('[' + _.keys(entityMap.escape).join('') + ']', 'g'),
    unescape: new RegExp('(' + _.keys(entityMap.unescape).join('|') + ')', 'g')
  };

  // Functions for escaping and unescaping strings to/from HTML interpolation.
  _.each(['escape', 'unescape'], function(method) {
    _[method] = function(string) {
      if (string == null) return '';
      return ('' + string).replace(entityRegexes[method], function(match) {
        return entityMap[method][match];
      });
    };
  });

  // If the value of the named property is a function then invoke it;
  // otherwise, return it.
  _.result = function(object, property) {
    if (object == null) return null;
    var value = object[property];
    return _.isFunction(value) ? value.call(object) : value;
  };

  // Add your own custom functions to the Underscore object.
  _.mixin = function(obj) {
    each(_.functions(obj), function(name){
      var func = _[name] = obj[name];
      _.prototype[name] = function() {
        var args = [this._wrapped];
        push.apply(args, arguments);
        return result.call(this, func.apply(_, args));
      };
    });
  };

  // Generate a unique integer id (unique within the entire client session).
  // Useful for temporary DOM ids.
  var idCounter = 0;
  _.uniqueId = function(prefix) {
    var id = ++idCounter + '';
    return prefix ? prefix + id : id;
  };

  // By default, Underscore uses ERB-style template delimiters, change the
  // following template settings to use alternative delimiters.
  _.templateSettings = {
    evaluate    : /<%([\s\S]+?)%>/g,
    interpolate : /<%=([\s\S]+?)%>/g,
    escape      : /<%-([\s\S]+?)%>/g
  };

  // When customizing `templateSettings`, if you don't want to define an
  // interpolation, evaluation or escaping regex, we need one that is
  // guaranteed not to match.
  var noMatch = /(.)^/;

  // Certain characters need to be escaped so that they can be put into a
  // string literal.
  var escapes = {
    "'":      "'",
    '\\':     '\\',
    '\r':     'r',
    '\n':     'n',
    '\t':     't',
    '\u2028': 'u2028',
    '\u2029': 'u2029'
  };

  var escaper = /\\|'|\r|\n|\t|\u2028|\u2029/g;

  // JavaScript micro-templating, similar to John Resig's implementation.
  // Underscore templating handles arbitrary delimiters, preserves whitespace,
  // and correctly escapes quotes within interpolated code.
  _.template = function(text, data, settings) {
    var render;
    settings = _.defaults({}, settings, _.templateSettings);

    // Combine delimiters into one regular expression via alternation.
    var matcher = new RegExp([
      (settings.escape || noMatch).source,
      (settings.interpolate || noMatch).source,
      (settings.evaluate || noMatch).source
    ].join('|') + '|$', 'g');

    // Compile the template source, escaping string literals appropriately.
    var index = 0;
    var source = "__p+='";
    text.replace(matcher, function(match, escape, interpolate, evaluate, offset) {
      source += text.slice(index, offset)
        .replace(escaper, function(match) { return '\\' + escapes[match]; });

      if (escape) {
        source += "'+\n((__t=(" + escape + "))==null?'':_.escape(__t))+\n'";
      }
      if (interpolate) {
        source += "'+\n((__t=(" + interpolate + "))==null?'':__t)+\n'";
      }
      if (evaluate) {
        source += "';\n" + evaluate + "\n__p+='";
      }
      index = offset + match.length;
      return match;
    });
    source += "';\n";

    // If a variable is not specified, place data values in local scope.
    if (!settings.variable) source = 'with(obj||{}){\n' + source + '}\n';

    source = "var __t,__p='',__j=Array.prototype.join," +
      "print=function(){__p+=__j.call(arguments,'');};\n" +
      source + "return __p;\n";

    try {
      render = new Function(settings.variable || 'obj', '_', source);
    } catch (e) {
      e.source = source;
      throw e;
    }

    if (data) return render(data, _);
    var template = function(data) {
      return render.call(this, data, _);
    };

    // Provide the compiled function source as a convenience for precompilation.
    template.source = 'function(' + (settings.variable || 'obj') + '){\n' + source + '}';

    return template;
  };

  // Add a "chain" function, which will delegate to the wrapper.
  _.chain = function(obj) {
    return _(obj).chain();
  };

  // OOP
  // ---------------
  // If Underscore is called as a function, it returns a wrapped object that
  // can be used OO-style. This wrapper holds altered versions of all the
  // underscore functions. Wrapped objects may be chained.

  // Helper function to continue chaining intermediate results.
  var result = function(obj) {
    return this._chain ? _(obj).chain() : obj;
  };

  // Add all of the Underscore functions to the wrapper object.
  _.mixin(_);

  // Add all mutator Array functions to the wrapper.
  each(['pop', 'push', 'reverse', 'shift', 'sort', 'splice', 'unshift'], function(name) {
    var method = ArrayProto[name];
    _.prototype[name] = function() {
      var obj = this._wrapped;
      method.apply(obj, arguments);
      if ((name == 'shift' || name == 'splice') && obj.length === 0) delete obj[0];
      return result.call(this, obj);
    };
  });

  // Add all accessor Array functions to the wrapper.
  each(['concat', 'join', 'slice'], function(name) {
    var method = ArrayProto[name];
    _.prototype[name] = function() {
      return result.call(this, method.apply(this._wrapped, arguments));
    };
  });

  _.extend(_.prototype, {

    // Start chaining a wrapped Underscore object.
    chain: function() {
      this._chain = true;
      return this;
    },

    // Extracts the result from a wrapped and chained object.
    value: function() {
      return this._wrapped;
    }

  });

}).call(this);
/**
 * @fileoverview
 * - Using the 'QRCode for Javascript library'
 * - Fixed dataset of 'QRCode for Javascript library' for support full-spec.
 * - this library has no dependencies.
 * 
 * @author davidshimjs
 * @see <a href="http://www.d-project.com/" target="_blank">http://www.d-project.com/</a>
 * @see <a href="http://jeromeetienne.github.com/jquery-qrcode/" target="_blank">http://jeromeetienne.github.com/jquery-qrcode/</a>
 */
var QRCode;

(function () {
    //---------------------------------------------------------------------
    // QRCode for JavaScript
    //
    // Copyright (c) 2009 Kazuhiko Arase
    //
    // URL: http://www.d-project.com/
    //
    // Licensed under the MIT license:
    //   http://www.opensource.org/licenses/mit-license.php
    //
    // The word "QR Code" is registered trademark of 
    // DENSO WAVE INCORPORATED
    //   http://www.denso-wave.com/qrcode/faqpatent-e.html
    //
    //---------------------------------------------------------------------
    function QR8bitByte(data) {
        this.mode = QRMode.MODE_8BIT_BYTE;
        this.data = data;
        this.parsedData = [];
        var byteArray = [];

        // Added to support UTF-8 Characters
        for (var i = 0, l = this.data.length; i < l; i++) {
            var code = this.data.charCodeAt(i);

            if (code > 0x10000) {
                byteArray[0] = 0xF0 | ((code & 0x1C0000) >>> 18);
                byteArray[1] = 0x80 | ((code & 0x3F000) >>> 12);
                byteArray[2] = 0x80 | ((code & 0xFC0) >>> 6);
                byteArray[3] = 0x80 | (code & 0x3F);
            } else if (code > 0x800) {
                byteArray[0] = 0xE0 | ((code & 0xF000) >>> 12);
                byteArray[1] = 0x80 | ((code & 0xFC0) >>> 6);
                byteArray[2] = 0x80 | (code & 0x3F);
            } else if (code > 0x80) {
                byteArray[0] = 0xC0 | ((code & 0x7C0) >>> 6);
                byteArray[1] = 0x80 | (code & 0x3F);
            } else {
                byteArray[0] = code;
            }

            this.parsedData = this.parsedData.concat(byteArray);
        }

        if (this.parsedData.length != this.data.length) {
            this.parsedData.unshift(191);
            this.parsedData.unshift(187);
            this.parsedData.unshift(239);
        }
    }

    QR8bitByte.prototype = {
        getLength: function (buffer) {
            return this.parsedData.length;
        },
        write: function (buffer) {
            for (var i = 0, l = this.parsedData.length; i < l; i++) {
                buffer.put(this.parsedData[i], 8);
            }
        }
    };

    function QRCodeModel(typeNumber, errorCorrectLevel) {
        this.typeNumber = typeNumber;
        this.errorCorrectLevel = errorCorrectLevel;
        this.modules = null;
        this.moduleCount = 0;
        this.dataCache = null;
        this.dataList = [];
    }

    QRCodeModel.prototype={addData:function(data){var newData=new QR8bitByte(data);this.dataList.push(newData);this.dataCache=null;},isDark:function(row,col){if(row<0||this.moduleCount<=row||col<0||this.moduleCount<=col){throw new Error(row+","+col);}
    return this.modules[row][col];},getModuleCount:function(){return this.moduleCount;},make:function(){this.makeImpl(false,this.getBestMaskPattern());},makeImpl:function(test,maskPattern){this.moduleCount=this.typeNumber*4+17;this.modules=new Array(this.moduleCount);for(var row=0;row<this.moduleCount;row++){this.modules[row]=new Array(this.moduleCount);for(var col=0;col<this.moduleCount;col++){this.modules[row][col]=null;}}
    this.setupPositionProbePattern(0,0);this.setupPositionProbePattern(this.moduleCount-7,0);this.setupPositionProbePattern(0,this.moduleCount-7);this.setupPositionAdjustPattern();this.setupTimingPattern();this.setupTypeInfo(test,maskPattern);if(this.typeNumber>=7){this.setupTypeNumber(test);}
    if(this.dataCache==null){this.dataCache=QRCodeModel.createData(this.typeNumber,this.errorCorrectLevel,this.dataList);}
    this.mapData(this.dataCache,maskPattern);},setupPositionProbePattern:function(row,col){for(var r=-1;r<=7;r++){if(row+r<=-1||this.moduleCount<=row+r)continue;for(var c=-1;c<=7;c++){if(col+c<=-1||this.moduleCount<=col+c)continue;if((0<=r&&r<=6&&(c==0||c==6))||(0<=c&&c<=6&&(r==0||r==6))||(2<=r&&r<=4&&2<=c&&c<=4)){this.modules[row+r][col+c]=true;}else{this.modules[row+r][col+c]=false;}}}},getBestMaskPattern:function(){var minLostPoint=0;var pattern=0;for(var i=0;i<8;i++){this.makeImpl(true,i);var lostPoint=QRUtil.getLostPoint(this);if(i==0||minLostPoint>lostPoint){minLostPoint=lostPoint;pattern=i;}}
    return pattern;},createMovieClip:function(target_mc,instance_name,depth){var qr_mc=target_mc.createEmptyMovieClip(instance_name,depth);var cs=1;this.make();for(var row=0;row<this.modules.length;row++){var y=row*cs;for(var col=0;col<this.modules[row].length;col++){var x=col*cs;var dark=this.modules[row][col];if(dark){qr_mc.beginFill(0,100);qr_mc.moveTo(x,y);qr_mc.lineTo(x+cs,y);qr_mc.lineTo(x+cs,y+cs);qr_mc.lineTo(x,y+cs);qr_mc.endFill();}}}
    return qr_mc;},setupTimingPattern:function(){for(var r=8;r<this.moduleCount-8;r++){if(this.modules[r][6]!=null){continue;}
    this.modules[r][6]=(r%2==0);}
    for(var c=8;c<this.moduleCount-8;c++){if(this.modules[6][c]!=null){continue;}
    this.modules[6][c]=(c%2==0);}},setupPositionAdjustPattern:function(){var pos=QRUtil.getPatternPosition(this.typeNumber);for(var i=0;i<pos.length;i++){for(var j=0;j<pos.length;j++){var row=pos[i];var col=pos[j];if(this.modules[row][col]!=null){continue;}
    for(var r=-2;r<=2;r++){for(var c=-2;c<=2;c++){if(r==-2||r==2||c==-2||c==2||(r==0&&c==0)){this.modules[row+r][col+c]=true;}else{this.modules[row+r][col+c]=false;}}}}}},setupTypeNumber:function(test){var bits=QRUtil.getBCHTypeNumber(this.typeNumber);for(var i=0;i<18;i++){var mod=(!test&&((bits>>i)&1)==1);this.modules[Math.floor(i/3)][i%3+this.moduleCount-8-3]=mod;}
    for(var i=0;i<18;i++){var mod=(!test&&((bits>>i)&1)==1);this.modules[i%3+this.moduleCount-8-3][Math.floor(i/3)]=mod;}},setupTypeInfo:function(test,maskPattern){var data=(this.errorCorrectLevel<<3)|maskPattern;var bits=QRUtil.getBCHTypeInfo(data);for(var i=0;i<15;i++){var mod=(!test&&((bits>>i)&1)==1);if(i<6){this.modules[i][8]=mod;}else if(i<8){this.modules[i+1][8]=mod;}else{this.modules[this.moduleCount-15+i][8]=mod;}}
    for(var i=0;i<15;i++){var mod=(!test&&((bits>>i)&1)==1);if(i<8){this.modules[8][this.moduleCount-i-1]=mod;}else if(i<9){this.modules[8][15-i-1+1]=mod;}else{this.modules[8][15-i-1]=mod;}}
    this.modules[this.moduleCount-8][8]=(!test);},mapData:function(data,maskPattern){var inc=-1;var row=this.moduleCount-1;var bitIndex=7;var byteIndex=0;for(var col=this.moduleCount-1;col>0;col-=2){if(col==6)col--;while(true){for(var c=0;c<2;c++){if(this.modules[row][col-c]==null){var dark=false;if(byteIndex<data.length){dark=(((data[byteIndex]>>>bitIndex)&1)==1);}
    var mask=QRUtil.getMask(maskPattern,row,col-c);if(mask){dark=!dark;}
    this.modules[row][col-c]=dark;bitIndex--;if(bitIndex==-1){byteIndex++;bitIndex=7;}}}
    row+=inc;if(row<0||this.moduleCount<=row){row-=inc;inc=-inc;break;}}}}};QRCodeModel.PAD0=0xEC;QRCodeModel.PAD1=0x11;QRCodeModel.createData=function(typeNumber,errorCorrectLevel,dataList){var rsBlocks=QRRSBlock.getRSBlocks(typeNumber,errorCorrectLevel);var buffer=new QRBitBuffer();for(var i=0;i<dataList.length;i++){var data=dataList[i];buffer.put(data.mode,4);buffer.put(data.getLength(),QRUtil.getLengthInBits(data.mode,typeNumber));data.write(buffer);}
    var totalDataCount=0;for(var i=0;i<rsBlocks.length;i++){totalDataCount+=rsBlocks[i].dataCount;}
    if(buffer.getLengthInBits()>totalDataCount*8){throw new Error("code length overflow. ("
    +buffer.getLengthInBits()
    +">"
    +totalDataCount*8
    +")");}
    if(buffer.getLengthInBits()+4<=totalDataCount*8){buffer.put(0,4);}
    while(buffer.getLengthInBits()%8!=0){buffer.putBit(false);}
    while(true){if(buffer.getLengthInBits()>=totalDataCount*8){break;}
    buffer.put(QRCodeModel.PAD0,8);if(buffer.getLengthInBits()>=totalDataCount*8){break;}
    buffer.put(QRCodeModel.PAD1,8);}
    return QRCodeModel.createBytes(buffer,rsBlocks);};QRCodeModel.createBytes=function(buffer,rsBlocks){var offset=0;var maxDcCount=0;var maxEcCount=0;var dcdata=new Array(rsBlocks.length);var ecdata=new Array(rsBlocks.length);for(var r=0;r<rsBlocks.length;r++){var dcCount=rsBlocks[r].dataCount;var ecCount=rsBlocks[r].totalCount-dcCount;maxDcCount=Math.max(maxDcCount,dcCount);maxEcCount=Math.max(maxEcCount,ecCount);dcdata[r]=new Array(dcCount);for(var i=0;i<dcdata[r].length;i++){dcdata[r][i]=0xff&buffer.buffer[i+offset];}
    offset+=dcCount;var rsPoly=QRUtil.getErrorCorrectPolynomial(ecCount);var rawPoly=new QRPolynomial(dcdata[r],rsPoly.getLength()-1);var modPoly=rawPoly.mod(rsPoly);ecdata[r]=new Array(rsPoly.getLength()-1);for(var i=0;i<ecdata[r].length;i++){var modIndex=i+modPoly.getLength()-ecdata[r].length;ecdata[r][i]=(modIndex>=0)?modPoly.get(modIndex):0;}}
    var totalCodeCount=0;for(var i=0;i<rsBlocks.length;i++){totalCodeCount+=rsBlocks[i].totalCount;}
    var data=new Array(totalCodeCount);var index=0;for(var i=0;i<maxDcCount;i++){for(var r=0;r<rsBlocks.length;r++){if(i<dcdata[r].length){data[index++]=dcdata[r][i];}}}
    for(var i=0;i<maxEcCount;i++){for(var r=0;r<rsBlocks.length;r++){if(i<ecdata[r].length){data[index++]=ecdata[r][i];}}}
    return data;};var QRMode={MODE_NUMBER:1<<0,MODE_ALPHA_NUM:1<<1,MODE_8BIT_BYTE:1<<2,MODE_KANJI:1<<3};var QRErrorCorrectLevel={L:1,M:0,Q:3,H:2};var QRMaskPattern={PATTERN000:0,PATTERN001:1,PATTERN010:2,PATTERN011:3,PATTERN100:4,PATTERN101:5,PATTERN110:6,PATTERN111:7};var QRUtil={PATTERN_POSITION_TABLE:[[],[6,18],[6,22],[6,26],[6,30],[6,34],[6,22,38],[6,24,42],[6,26,46],[6,28,50],[6,30,54],[6,32,58],[6,34,62],[6,26,46,66],[6,26,48,70],[6,26,50,74],[6,30,54,78],[6,30,56,82],[6,30,58,86],[6,34,62,90],[6,28,50,72,94],[6,26,50,74,98],[6,30,54,78,102],[6,28,54,80,106],[6,32,58,84,110],[6,30,58,86,114],[6,34,62,90,118],[6,26,50,74,98,122],[6,30,54,78,102,126],[6,26,52,78,104,130],[6,30,56,82,108,134],[6,34,60,86,112,138],[6,30,58,86,114,142],[6,34,62,90,118,146],[6,30,54,78,102,126,150],[6,24,50,76,102,128,154],[6,28,54,80,106,132,158],[6,32,58,84,110,136,162],[6,26,54,82,110,138,166],[6,30,58,86,114,142,170]],G15:(1<<10)|(1<<8)|(1<<5)|(1<<4)|(1<<2)|(1<<1)|(1<<0),G18:(1<<12)|(1<<11)|(1<<10)|(1<<9)|(1<<8)|(1<<5)|(1<<2)|(1<<0),G15_MASK:(1<<14)|(1<<12)|(1<<10)|(1<<4)|(1<<1),getBCHTypeInfo:function(data){var d=data<<10;while(QRUtil.getBCHDigit(d)-QRUtil.getBCHDigit(QRUtil.G15)>=0){d^=(QRUtil.G15<<(QRUtil.getBCHDigit(d)-QRUtil.getBCHDigit(QRUtil.G15)));}
    return((data<<10)|d)^QRUtil.G15_MASK;},getBCHTypeNumber:function(data){var d=data<<12;while(QRUtil.getBCHDigit(d)-QRUtil.getBCHDigit(QRUtil.G18)>=0){d^=(QRUtil.G18<<(QRUtil.getBCHDigit(d)-QRUtil.getBCHDigit(QRUtil.G18)));}
    return(data<<12)|d;},getBCHDigit:function(data){var digit=0;while(data!=0){digit++;data>>>=1;}
    return digit;},getPatternPosition:function(typeNumber){return QRUtil.PATTERN_POSITION_TABLE[typeNumber-1];},getMask:function(maskPattern,i,j){switch(maskPattern){case QRMaskPattern.PATTERN000:return(i+j)%2==0;case QRMaskPattern.PATTERN001:return i%2==0;case QRMaskPattern.PATTERN010:return j%3==0;case QRMaskPattern.PATTERN011:return(i+j)%3==0;case QRMaskPattern.PATTERN100:return(Math.floor(i/2)+Math.floor(j/3))%2==0;case QRMaskPattern.PATTERN101:return(i*j)%2+(i*j)%3==0;case QRMaskPattern.PATTERN110:return((i*j)%2+(i*j)%3)%2==0;case QRMaskPattern.PATTERN111:return((i*j)%3+(i+j)%2)%2==0;default:throw new Error("bad maskPattern:"+maskPattern);}},getErrorCorrectPolynomial:function(errorCorrectLength){var a=new QRPolynomial([1],0);for(var i=0;i<errorCorrectLength;i++){a=a.multiply(new QRPolynomial([1,QRMath.gexp(i)],0));}
    return a;},getLengthInBits:function(mode,type){if(1<=type&&type<10){switch(mode){case QRMode.MODE_NUMBER:return 10;case QRMode.MODE_ALPHA_NUM:return 9;case QRMode.MODE_8BIT_BYTE:return 8;case QRMode.MODE_KANJI:return 8;default:throw new Error("mode:"+mode);}}else if(type<27){switch(mode){case QRMode.MODE_NUMBER:return 12;case QRMode.MODE_ALPHA_NUM:return 11;case QRMode.MODE_8BIT_BYTE:return 16;case QRMode.MODE_KANJI:return 10;default:throw new Error("mode:"+mode);}}else if(type<41){switch(mode){case QRMode.MODE_NUMBER:return 14;case QRMode.MODE_ALPHA_NUM:return 13;case QRMode.MODE_8BIT_BYTE:return 16;case QRMode.MODE_KANJI:return 12;default:throw new Error("mode:"+mode);}}else{throw new Error("type:"+type);}},getLostPoint:function(qrCode){var moduleCount=qrCode.getModuleCount();var lostPoint=0;for(var row=0;row<moduleCount;row++){for(var col=0;col<moduleCount;col++){var sameCount=0;var dark=qrCode.isDark(row,col);for(var r=-1;r<=1;r++){if(row+r<0||moduleCount<=row+r){continue;}
    for(var c=-1;c<=1;c++){if(col+c<0||moduleCount<=col+c){continue;}
    if(r==0&&c==0){continue;}
    if(dark==qrCode.isDark(row+r,col+c)){sameCount++;}}}
    if(sameCount>5){lostPoint+=(3+sameCount-5);}}}
    for(var row=0;row<moduleCount-1;row++){for(var col=0;col<moduleCount-1;col++){var count=0;if(qrCode.isDark(row,col))count++;if(qrCode.isDark(row+1,col))count++;if(qrCode.isDark(row,col+1))count++;if(qrCode.isDark(row+1,col+1))count++;if(count==0||count==4){lostPoint+=3;}}}
    for(var row=0;row<moduleCount;row++){for(var col=0;col<moduleCount-6;col++){if(qrCode.isDark(row,col)&&!qrCode.isDark(row,col+1)&&qrCode.isDark(row,col+2)&&qrCode.isDark(row,col+3)&&qrCode.isDark(row,col+4)&&!qrCode.isDark(row,col+5)&&qrCode.isDark(row,col+6)){lostPoint+=40;}}}
    for(var col=0;col<moduleCount;col++){for(var row=0;row<moduleCount-6;row++){if(qrCode.isDark(row,col)&&!qrCode.isDark(row+1,col)&&qrCode.isDark(row+2,col)&&qrCode.isDark(row+3,col)&&qrCode.isDark(row+4,col)&&!qrCode.isDark(row+5,col)&&qrCode.isDark(row+6,col)){lostPoint+=40;}}}
    var darkCount=0;for(var col=0;col<moduleCount;col++){for(var row=0;row<moduleCount;row++){if(qrCode.isDark(row,col)){darkCount++;}}}
    var ratio=Math.abs(100*darkCount/moduleCount/moduleCount-50)/5;lostPoint+=ratio*10;return lostPoint;}};var QRMath={glog:function(n){if(n<1){throw new Error("glog("+n+")");}
    return QRMath.LOG_TABLE[n];},gexp:function(n){while(n<0){n+=255;}
    while(n>=256){n-=255;}
    return QRMath.EXP_TABLE[n];},EXP_TABLE:new Array(256),LOG_TABLE:new Array(256)};for(var i=0;i<8;i++){QRMath.EXP_TABLE[i]=1<<i;}
    for(var i=8;i<256;i++){QRMath.EXP_TABLE[i]=QRMath.EXP_TABLE[i-4]^QRMath.EXP_TABLE[i-5]^QRMath.EXP_TABLE[i-6]^QRMath.EXP_TABLE[i-8];}
    for(var i=0;i<255;i++){QRMath.LOG_TABLE[QRMath.EXP_TABLE[i]]=i;}
    function QRPolynomial(num,shift){if(num.length==undefined){throw new Error(num.length+"/"+shift);}
    var offset=0;while(offset<num.length&&num[offset]==0){offset++;}
    this.num=new Array(num.length-offset+shift);for(var i=0;i<num.length-offset;i++){this.num[i]=num[i+offset];}}
    QRPolynomial.prototype={get:function(index){return this.num[index];},getLength:function(){return this.num.length;},multiply:function(e){var num=new Array(this.getLength()+e.getLength()-1);for(var i=0;i<this.getLength();i++){for(var j=0;j<e.getLength();j++){num[i+j]^=QRMath.gexp(QRMath.glog(this.get(i))+QRMath.glog(e.get(j)));}}
    return new QRPolynomial(num,0);},mod:function(e){if(this.getLength()-e.getLength()<0){return this;}
    var ratio=QRMath.glog(this.get(0))-QRMath.glog(e.get(0));var num=new Array(this.getLength());for(var i=0;i<this.getLength();i++){num[i]=this.get(i);}
    for(var i=0;i<e.getLength();i++){num[i]^=QRMath.gexp(QRMath.glog(e.get(i))+ratio);}
    return new QRPolynomial(num,0).mod(e);}};function QRRSBlock(totalCount,dataCount){this.totalCount=totalCount;this.dataCount=dataCount;}
    QRRSBlock.RS_BLOCK_TABLE=[[1,26,19],[1,26,16],[1,26,13],[1,26,9],[1,44,34],[1,44,28],[1,44,22],[1,44,16],[1,70,55],[1,70,44],[2,35,17],[2,35,13],[1,100,80],[2,50,32],[2,50,24],[4,25,9],[1,134,108],[2,67,43],[2,33,15,2,34,16],[2,33,11,2,34,12],[2,86,68],[4,43,27],[4,43,19],[4,43,15],[2,98,78],[4,49,31],[2,32,14,4,33,15],[4,39,13,1,40,14],[2,121,97],[2,60,38,2,61,39],[4,40,18,2,41,19],[4,40,14,2,41,15],[2,146,116],[3,58,36,2,59,37],[4,36,16,4,37,17],[4,36,12,4,37,13],[2,86,68,2,87,69],[4,69,43,1,70,44],[6,43,19,2,44,20],[6,43,15,2,44,16],[4,101,81],[1,80,50,4,81,51],[4,50,22,4,51,23],[3,36,12,8,37,13],[2,116,92,2,117,93],[6,58,36,2,59,37],[4,46,20,6,47,21],[7,42,14,4,43,15],[4,133,107],[8,59,37,1,60,38],[8,44,20,4,45,21],[12,33,11,4,34,12],[3,145,115,1,146,116],[4,64,40,5,65,41],[11,36,16,5,37,17],[11,36,12,5,37,13],[5,109,87,1,110,88],[5,65,41,5,66,42],[5,54,24,7,55,25],[11,36,12],[5,122,98,1,123,99],[7,73,45,3,74,46],[15,43,19,2,44,20],[3,45,15,13,46,16],[1,135,107,5,136,108],[10,74,46,1,75,47],[1,50,22,15,51,23],[2,42,14,17,43,15],[5,150,120,1,151,121],[9,69,43,4,70,44],[17,50,22,1,51,23],[2,42,14,19,43,15],[3,141,113,4,142,114],[3,70,44,11,71,45],[17,47,21,4,48,22],[9,39,13,16,40,14],[3,135,107,5,136,108],[3,67,41,13,68,42],[15,54,24,5,55,25],[15,43,15,10,44,16],[4,144,116,4,145,117],[17,68,42],[17,50,22,6,51,23],[19,46,16,6,47,17],[2,139,111,7,140,112],[17,74,46],[7,54,24,16,55,25],[34,37,13],[4,151,121,5,152,122],[4,75,47,14,76,48],[11,54,24,14,55,25],[16,45,15,14,46,16],[6,147,117,4,148,118],[6,73,45,14,74,46],[11,54,24,16,55,25],[30,46,16,2,47,17],[8,132,106,4,133,107],[8,75,47,13,76,48],[7,54,24,22,55,25],[22,45,15,13,46,16],[10,142,114,2,143,115],[19,74,46,4,75,47],[28,50,22,6,51,23],[33,46,16,4,47,17],[8,152,122,4,153,123],[22,73,45,3,74,46],[8,53,23,26,54,24],[12,45,15,28,46,16],[3,147,117,10,148,118],[3,73,45,23,74,46],[4,54,24,31,55,25],[11,45,15,31,46,16],[7,146,116,7,147,117],[21,73,45,7,74,46],[1,53,23,37,54,24],[19,45,15,26,46,16],[5,145,115,10,146,116],[19,75,47,10,76,48],[15,54,24,25,55,25],[23,45,15,25,46,16],[13,145,115,3,146,116],[2,74,46,29,75,47],[42,54,24,1,55,25],[23,45,15,28,46,16],[17,145,115],[10,74,46,23,75,47],[10,54,24,35,55,25],[19,45,15,35,46,16],[17,145,115,1,146,116],[14,74,46,21,75,47],[29,54,24,19,55,25],[11,45,15,46,46,16],[13,145,115,6,146,116],[14,74,46,23,75,47],[44,54,24,7,55,25],[59,46,16,1,47,17],[12,151,121,7,152,122],[12,75,47,26,76,48],[39,54,24,14,55,25],[22,45,15,41,46,16],[6,151,121,14,152,122],[6,75,47,34,76,48],[46,54,24,10,55,25],[2,45,15,64,46,16],[17,152,122,4,153,123],[29,74,46,14,75,47],[49,54,24,10,55,25],[24,45,15,46,46,16],[4,152,122,18,153,123],[13,74,46,32,75,47],[48,54,24,14,55,25],[42,45,15,32,46,16],[20,147,117,4,148,118],[40,75,47,7,76,48],[43,54,24,22,55,25],[10,45,15,67,46,16],[19,148,118,6,149,119],[18,75,47,31,76,48],[34,54,24,34,55,25],[20,45,15,61,46,16]];QRRSBlock.getRSBlocks=function(typeNumber,errorCorrectLevel){var rsBlock=QRRSBlock.getRsBlockTable(typeNumber,errorCorrectLevel);if(rsBlock==undefined){throw new Error("bad rs block @ typeNumber:"+typeNumber+"/errorCorrectLevel:"+errorCorrectLevel);}
    var length=rsBlock.length/3;var list=[];for(var i=0;i<length;i++){var count=rsBlock[i*3+0];var totalCount=rsBlock[i*3+1];var dataCount=rsBlock[i*3+2];for(var j=0;j<count;j++){list.push(new QRRSBlock(totalCount,dataCount));}}
    return list;};QRRSBlock.getRsBlockTable=function(typeNumber,errorCorrectLevel){switch(errorCorrectLevel){case QRErrorCorrectLevel.L:return QRRSBlock.RS_BLOCK_TABLE[(typeNumber-1)*4+0];case QRErrorCorrectLevel.M:return QRRSBlock.RS_BLOCK_TABLE[(typeNumber-1)*4+1];case QRErrorCorrectLevel.Q:return QRRSBlock.RS_BLOCK_TABLE[(typeNumber-1)*4+2];case QRErrorCorrectLevel.H:return QRRSBlock.RS_BLOCK_TABLE[(typeNumber-1)*4+3];default:return undefined;}};function QRBitBuffer(){this.buffer=[];this.length=0;}
    QRBitBuffer.prototype={get:function(index){var bufIndex=Math.floor(index/8);return((this.buffer[bufIndex]>>>(7-index%8))&1)==1;},put:function(num,length){for(var i=0;i<length;i++){this.putBit(((num>>>(length-i-1))&1)==1);}},getLengthInBits:function(){return this.length;},putBit:function(bit){var bufIndex=Math.floor(this.length/8);if(this.buffer.length<=bufIndex){this.buffer.push(0);}
    if(bit){this.buffer[bufIndex]|=(0x80>>>(this.length%8));}
    this.length++;}};var QRCodeLimitLength=[[17,14,11,7],[32,26,20,14],[53,42,32,24],[78,62,46,34],[106,84,60,44],[134,106,74,58],[154,122,86,64],[192,152,108,84],[230,180,130,98],[271,213,151,119],[321,251,177,137],[367,287,203,155],[425,331,241,177],[458,362,258,194],[520,412,292,220],[586,450,322,250],[644,504,364,280],[718,560,394,310],[792,624,442,338],[858,666,482,382],[929,711,509,403],[1003,779,565,439],[1091,857,611,461],[1171,911,661,511],[1273,997,715,535],[1367,1059,751,593],[1465,1125,805,625],[1528,1190,868,658],[1628,1264,908,698],[1732,1370,982,742],[1840,1452,1030,790],[1952,1538,1112,842],[2068,1628,1168,898],[2188,1722,1228,958],[2303,1809,1283,983],[2431,1911,1351,1051],[2563,1989,1423,1093],[2699,2099,1499,1139],[2809,2213,1579,1219],[2953,2331,1663,1273]];
    
    function _isSupportCanvas() {
        return typeof CanvasRenderingContext2D != "undefined";
    }
    
    // android 2.x doesn't support Data-URI spec
    function _getAndroid() {
        var android = false;
        var sAgent = navigator.userAgent;
        
        if (/android/i.test(sAgent)) { // android
            android = true;
            aMat = sAgent.toString().match(/android ([0-9]\.[0-9])/i);
            
            if (aMat && aMat[1]) {
                android = parseFloat(aMat[1]);
            }
        }
        
        return android;
    }
    
    var svgDrawer = (function() {

        var Drawing = function (el, htOption) {
            this._el = el;
            this._htOption = htOption;
        };

        Drawing.prototype.draw = function (oQRCode) {
            var _htOption = this._htOption;
            var _el = this._el;
            var nCount = oQRCode.getModuleCount();
            var nWidth = Math.floor(_htOption.width / nCount);
            var nHeight = Math.floor(_htOption.height / nCount);

            this.clear();

            function makeSVG(tag, attrs) {
                var el = document.createElementNS('http://www.w3.org/2000/svg', tag);
                for (var k in attrs)
                    if (attrs.hasOwnProperty(k)) el.setAttribute(k, attrs[k]);
                return el;
            }

            var svg = makeSVG("svg" , {'viewBox': '0 0 ' + String(nCount) + " " + String(nCount), 'width': '100%', 'height': '100%', 'fill': _htOption.colorLight});
            svg.setAttributeNS("http://www.w3.org/2000/xmlns/", "xmlns:xlink", "http://www.w3.org/1999/xlink");
            _el.appendChild(svg);

            svg.appendChild(makeSVG("rect", {"fill": _htOption.colorDark, "width": "1", "height": "1", "id": "template"}));

            for (var row = 0; row < nCount; row++) {
                for (var col = 0; col < nCount; col++) {
                    if (oQRCode.isDark(row, col)) {
                        var child = makeSVG("use", {"x": String(row), "y": String(col)});
                        child.setAttributeNS("http://www.w3.org/1999/xlink", "href", "#template")
                        svg.appendChild(child);
                    }
                }
            }
        };
        Drawing.prototype.clear = function () {
            while (this._el.hasChildNodes())
                this._el.removeChild(this._el.lastChild);
        };
        return Drawing;
    })();

    var useSVG = document.documentElement.tagName.toLowerCase() === "svg";

    // Drawing in DOM by using Table tag
    var Drawing = useSVG ? svgDrawer : !_isSupportCanvas() ? (function () {
        var Drawing = function (el, htOption) {
            this._el = el;
            this._htOption = htOption;
        };
            
        /**
         * Draw the QRCode
         * 
         * @param {QRCode} oQRCode
         */
        Drawing.prototype.draw = function (oQRCode) {
            var _htOption = this._htOption;
            var _el = this._el;
            var nCount = oQRCode.getModuleCount();
            var nWidth = Math.floor(_htOption.width / nCount);
            var nHeight = Math.floor(_htOption.height / nCount);
            var aHTML = ['<table style="border:0;border-collapse:collapse;">'];
            
            for (var row = 0; row < nCount; row++) {
                aHTML.push('<tr>');
                
                for (var col = 0; col < nCount; col++) {
                    aHTML.push('<td style="border:0;border-collapse:collapse;padding:0;margin:0;width:' + nWidth + 'px;height:' + nHeight + 'px;background-color:' + (oQRCode.isDark(row, col) ? _htOption.colorDark : _htOption.colorLight) + ';"></td>');
                }
                
                aHTML.push('</tr>');
            }
            
            aHTML.push('</table>');
            _el.innerHTML = aHTML.join('');
            
            // Fix the margin values as real size.
            var elTable = _el.childNodes[0];
            var nLeftMarginTable = (_htOption.width - elTable.offsetWidth) / 2;
            var nTopMarginTable = (_htOption.height - elTable.offsetHeight) / 2;
            
            if (nLeftMarginTable > 0 && nTopMarginTable > 0) {
                elTable.style.margin = nTopMarginTable + "px " + nLeftMarginTable + "px";   
            }
        };
        
        /**
         * Clear the QRCode
         */
        Drawing.prototype.clear = function () {
            this._el.innerHTML = '';
        };
        
        return Drawing;
    })() : (function () { // Drawing in Canvas
        function _onMakeImage() {
            this._elImage.src = this._elCanvas.toDataURL("image/png");
            this._elImage.style.display = "block";
            this._elCanvas.style.display = "none";          
        }
        
        // Android 2.1 bug workaround
        // http://code.google.com/p/android/issues/detail?id=5141
        if (this._android && this._android <= 2.1) {
            var factor = 1 / window.devicePixelRatio;
            var drawImage = CanvasRenderingContext2D.prototype.drawImage; 
            CanvasRenderingContext2D.prototype.drawImage = function (image, sx, sy, sw, sh, dx, dy, dw, dh) {
                if (("nodeName" in image) && /img/i.test(image.nodeName)) {
                    for (var i = arguments.length - 1; i >= 1; i--) {
                        arguments[i] = arguments[i] * factor;
                    }
                } else if (typeof dw == "undefined") {
                    arguments[1] *= factor;
                    arguments[2] *= factor;
                    arguments[3] *= factor;
                    arguments[4] *= factor;
                }
                
                drawImage.apply(this, arguments); 
            };
        }
        
        /**
         * Check whether the user's browser supports Data URI or not
         * 
         * @private
         * @param {Function} fSuccess Occurs if it supports Data URI
         * @param {Function} fFail Occurs if it doesn't support Data URI
         */
        function _safeSetDataURI(fSuccess, fFail) {
            var self = this;
            self._fFail = fFail;
            self._fSuccess = fSuccess;

            // Check it just once
            if (self._bSupportDataURI === null) {
                var el = document.createElement("img");
                var fOnError = function() {
                    self._bSupportDataURI = false;

                    if (self._fFail) {
                        _fFail.call(self);
                    }
                };
                var fOnSuccess = function() {
                    self._bSupportDataURI = true;

                    if (self._fSuccess) {
                        self._fSuccess.call(self);
                    }
                };

                el.onabort = fOnError;
                el.onerror = fOnError;
                el.onload = fOnSuccess;
                el.src = "data:image/gif;base64,iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="; // the Image contains 1px data.
                return;
            } else if (self._bSupportDataURI === true && self._fSuccess) {
                self._fSuccess.call(self);
            } else if (self._bSupportDataURI === false && self._fFail) {
                self._fFail.call(self);
            }
        };
        
        /**
         * Drawing QRCode by using canvas
         * 
         * @constructor
         * @param {HTMLElement} el
         * @param {Object} htOption QRCode Options 
         */
        var Drawing = function (el, htOption) {
            this._bIsPainted = false;
            this._android = _getAndroid();
        
            this._htOption = htOption;
            this._elCanvas = document.createElement("canvas");
            this._elCanvas.width = htOption.width;
            this._elCanvas.height = htOption.height;
            el.appendChild(this._elCanvas);
            this._el = el;
            this._oContext = this._elCanvas.getContext("2d");
            this._bIsPainted = false;
            this._elImage = document.createElement("img");
            this._elImage.style.display = "none";
            this._el.appendChild(this._elImage);
            this._bSupportDataURI = null;
        };
            
        /**
         * Draw the QRCode
         * 
         * @param {QRCode} oQRCode 
         */
        Drawing.prototype.draw = function (oQRCode) {
            var _elImage = this._elImage;
            var _oContext = this._oContext;
            var _htOption = this._htOption;
            
            var nCount = oQRCode.getModuleCount();
            var nWidth = _htOption.width / nCount;
            var nHeight = _htOption.height / nCount;
            var nRoundedWidth = Math.round(nWidth);
            var nRoundedHeight = Math.round(nHeight);

            _elImage.style.display = "none";
            this.clear();
            
            for (var row = 0; row < nCount; row++) {
                for (var col = 0; col < nCount; col++) {
                    var bIsDark = oQRCode.isDark(row, col);
                    var nLeft = col * nWidth;
                    var nTop = row * nHeight;
                    _oContext.strokeStyle = bIsDark ? _htOption.colorDark : _htOption.colorLight;
                    _oContext.lineWidth = 1;
                    _oContext.fillStyle = bIsDark ? _htOption.colorDark : _htOption.colorLight;                 
                    _oContext.fillRect(nLeft, nTop, nWidth, nHeight);
                    
                    // 안티 앨리어싱 방지 처리
                    _oContext.strokeRect(
                        Math.floor(nLeft) + 0.5,
                        Math.floor(nTop) + 0.5,
                        nRoundedWidth,
                        nRoundedHeight
                    );
                    
                    _oContext.strokeRect(
                        Math.ceil(nLeft) - 0.5,
                        Math.ceil(nTop) - 0.5,
                        nRoundedWidth,
                        nRoundedHeight
                    );
                }
            }
            
            this._bIsPainted = true;
        };
            
        /**
         * Make the image from Canvas if the browser supports Data URI.
         */
        Drawing.prototype.makeImage = function () {
            if (this._bIsPainted) {
                _safeSetDataURI.call(this, _onMakeImage);
            }
        };
            
        /**
         * Return whether the QRCode is painted or not
         * 
         * @return {Boolean}
         */
        Drawing.prototype.isPainted = function () {
            return this._bIsPainted;
        };
        
        /**
         * Clear the QRCode
         */
        Drawing.prototype.clear = function () {
            this._oContext.clearRect(0, 0, this._elCanvas.width, this._elCanvas.height);
            this._bIsPainted = false;
        };
        
        /**
         * @private
         * @param {Number} nNumber
         */
        Drawing.prototype.round = function (nNumber) {
            if (!nNumber) {
                return nNumber;
            }
            
            return Math.floor(nNumber * 1000) / 1000;
        };
        
        return Drawing;
    })();
    
    /**
     * Get the type by string length
     * 
     * @private
     * @param {String} sText
     * @param {Number} nCorrectLevel
     * @return {Number} type
     */
    function _getTypeNumber(sText, nCorrectLevel) {         
        var nType = 1;
        var length = _getUTF8Length(sText);
        
        for (var i = 0, len = QRCodeLimitLength.length; i <= len; i++) {
            var nLimit = 0;
            
            switch (nCorrectLevel) {
                case QRErrorCorrectLevel.L :
                    nLimit = QRCodeLimitLength[i][0];
                    break;
                case QRErrorCorrectLevel.M :
                    nLimit = QRCodeLimitLength[i][1];
                    break;
                case QRErrorCorrectLevel.Q :
                    nLimit = QRCodeLimitLength[i][2];
                    break;
                case QRErrorCorrectLevel.H :
                    nLimit = QRCodeLimitLength[i][3];
                    break;
            }
            
            if (length <= nLimit) {
                break;
            } else {
                nType++;
            }
        }
        
        if (nType > QRCodeLimitLength.length) {
            throw new Error("Too long data");
        }
        
        return nType;
    }

    function _getUTF8Length(sText) {
        var replacedText = encodeURI(sText).toString().replace(/\%[0-9a-fA-F]{2}/g, 'a');
        return replacedText.length + (replacedText.length != sText ? 3 : 0);
    }
    
    /**
     * @class QRCode
     * @constructor
     * @example 
     * new QRCode(document.getElementById("test"), "http://jindo.dev.naver.com/collie");
     *
     * @example
     * var oQRCode = new QRCode("test", {
     *    text : "http://naver.com",
     *    width : 128,
     *    height : 128
     * });
     * 
     * oQRCode.clear(); // Clear the QRCode.
     * oQRCode.makeCode("http://map.naver.com"); // Re-create the QRCode.
     *
     * @param {HTMLElement|String} el target element or 'id' attribute of element.
     * @param {Object|String} vOption
     * @param {String} vOption.text QRCode link data
     * @param {Number} [vOption.width=256]
     * @param {Number} [vOption.height=256]
     * @param {String} [vOption.colorDark="#000000"]
     * @param {String} [vOption.colorLight="#ffffff"]
     * @param {QRCode.CorrectLevel} [vOption.correctLevel=QRCode.CorrectLevel.H] [L|M|Q|H] 
     */
    QRCode = function (el, vOption) {
        this._htOption = {
            width : 256, 
            height : 256,
            typeNumber : 4,
            colorDark : "#000000",
            colorLight : "#ffffff",
            correctLevel : QRErrorCorrectLevel.H
        };
        
        if (typeof vOption === 'string') {
            vOption = {
                text : vOption
            };
        }
        
        // Overwrites options
        if (vOption) {
            for (var i in vOption) {
                this._htOption[i] = vOption[i];
            }
        }
        
        if (typeof el == "string") {
            el = document.getElementById(el);
        }
        
        this._android = _getAndroid();
        this._el = el;
        this._oQRCode = null;
        this._oDrawing = new Drawing(this._el, this._htOption);
        
        if (this._htOption.text) {
            this.makeCode(this._htOption.text); 
        }
    };
    
    /**
     * Make the QRCode
     * 
     * @param {String} sText link data
     */
    QRCode.prototype.makeCode = function (sText) {
        this._oQRCode = new QRCodeModel(_getTypeNumber(sText, this._htOption.correctLevel), this._htOption.correctLevel);
        this._oQRCode.addData(sText);
        this._oQRCode.make();
        this._el.title = sText;
        this._oDrawing.draw(this._oQRCode);         
        this.makeImage();
    };
    
    /**
     * Make the Image from Canvas element
     * - It occurs automatically
     * - Android below 3 doesn't support Data-URI spec.
     * 
     * @private
     */
    QRCode.prototype.makeImage = function () {
        if (typeof this._oDrawing.makeImage == "function" && (!this._android || this._android >= 3)) {
            this._oDrawing.makeImage();
        }
    };
    
    /**
     * Clear the QRCode
     */
    QRCode.prototype.clear = function () {
        this._oDrawing.clear();
    };
    
    /**
     * @name QRCode.CorrectLevel
     */
    QRCode.CorrectLevel = QRErrorCorrectLevel;
})();
