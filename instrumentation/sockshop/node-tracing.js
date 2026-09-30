/* Node 4 compatible experiment hook. Preload before server.js.
 * Domains carry per-request context across the legacy callback-based app.
 * Never infer parentage from timing or a global "last request" variable.
 */
'use strict';
var http = require('http');
var https = require('https');
var url = require('url');
var domain = require('domain');
var crypto = require('crypto');
var nativeRequest = http.request;
var endpoint = url.parse(process.env.TRACE_ENDPOINT || 'http://trace-collector:9411/api/v2/spans');
var service = process.env.TRACE_SERVICE || 'front-end';

function id(bytes) { return crypto.randomBytes(bytes).toString('hex'); }
function context(value) {
  var m = /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/.exec(value || '');
  if (m && !/^0+$/.test(m[1]) && !/^0+$/.test(m[2])) return {trace: m[1], parent: m[2]};
  return {trace: id(16), parent: null};
}
function emit(span) {
  var body = JSON.stringify([span]);
  var options = {hostname: endpoint.hostname, port: endpoint.port, path: endpoint.path,
    method: 'POST', headers: {'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body)}};
  var request = nativeRequest(options, function (res) {
    res.resume();
    if (res.statusCode !== 202) console.error('TF2_EXPORT_ERROR status=' + res.statusCode);
  });
  request.on('error', function (err) { console.error('TF2_EXPORT_ERROR ' + err.message); });
  request.setTimeout(5000, function () { request.abort(); });
  request.end(body);
}
function span(ctx, name, kind) {
  var s = {traceId: ctx.trace, id: id(8), name: name, kind: kind,
    timestamp: Date.now() * 1000, localEndpoint: {serviceName: service}, tags: {}};
  if (ctx.parent) s.parentId = ctx.parent;
  return s;
}
function finisher(s) {
  var start = process.hrtime();
  var done = false;
  return function (error) {
    if (done) return;
    done = true;
    var delta = process.hrtime(start);
    s.duration = Math.max(1, delta[0] * 1000000 + Math.floor(delta[1] / 1000));
    if (error) s.tags.error = String(error);
    emit(s);
  };
}
var nativeEmit = http.Server.prototype.emit;
http.Server.prototype.emit = function (event, req, res) {
  if (event !== 'request') return nativeEmit.apply(this, arguments);
  var server = this;
  var s = span(context(req.headers.traceparent), req.method + ' ' + req.url.split('?')[0], 'SERVER');
  s.tags['http.method'] = req.method;
  s.tags['http.target'] = req.url;
  var finish = finisher(s);
  var scope = domain.create();
  scope.tf2 = {trace: s.traceId, parent: s.id};
  scope.add(req);
  scope.add(res);
  res.once('finish', function () { s.tags['http.status_code'] = String(res.statusCode); finish(); });
  res.once('close', function () { if (!res.finished) finish('response_closed'); });
  return scope.run(function () { return nativeEmit.call(server, event, req, res); });
};
function instrument(mod) {
  var original = mod.request;
  mod.request = function (input, callback) {
    var current = process.domain && process.domain.tf2;
    if (!current) return original.apply(this, arguments);
    var options = typeof input === 'string' ? url.parse(input) : input;
    var copy = {}, headers = {};
    Object.keys(options).forEach(function (key) { copy[key] = options[key]; });
    Object.keys(options.headers || {}).forEach(function (key) {
      if (key.toLowerCase() !== 'traceparent' && key.toLowerCase() !== 'tracestate') headers[key] = options.headers[key];
    });
    var path = options.path || '/';
    var s = span(current, (options.method || 'GET') + ' ' + path.split('?')[0], 'CLIENT');
    s.tags['http.method'] = options.method || 'GET';
    s.tags['http.url'] = (options.protocol || (mod === https ? 'https:' : 'http:')) + '//' +
      (options.hostname || options.host || 'localhost') + ':' + (options.port || (mod === https ? 443 : 80)) + path;
    headers.traceparent = '00-' + s.traceId + '-' + s.id + '-01';
    copy.headers = headers;
    var finish = finisher(s), request;
    try { request = original.call(mod, copy, callback); }
    catch (err) { finish(err.message); throw err; }
    request.once('response', function (res) {
      s.tags['http.status_code'] = String(res.statusCode);
      res.once('end', function () { finish(); });
      res.once('aborted', function () { finish('response_aborted'); });
      res.once('error', function (err) { finish(err.message); });
    });
    request.once('error', function (err) { finish(err.message); });
    request.once('abort', function () { finish('request_aborted'); });
    return request;
  };
  mod.get = function (options, callback) {
    var request = mod.request(options, callback);
    request.end();
    return request;
  };
}
instrument(http);
instrument(https);
