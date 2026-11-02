(function () {
  'use strict';

  var CHANNEL = 'dev-sequence-prototype';
  var PROTOCOL_VERSION = 5;
  var manifestElement = document.getElementById('prototype-manifest');
  var manifest;
  try { manifest = JSON.parse(manifestElement.textContent); }
  catch (error) { console.error('[dev-sequence] Invalid prototype manifest', error); return; }

  var inFrame = window.self !== window.top;
  var root = document.querySelector('[data-ds-prototype-root]') || document.getElementById('root') || document.body;
  var baseLayer = document.getElementById('pdBaseMarkerLayer');
  var overlayMarkerHost = document.getElementById('pdOverlayMarkerHost');
  var markerRecords = [];
  var managedOverlayRoots = [];
  var overlayLayers = {};
  var topBlockingOverlayDepth = 0;
  var markerFrame = 0;
  var sizeFrame = 0;
  var rootStyle = getComputedStyle(document.documentElement);
  var markerSize = parseFloat(rootStyle.getPropertyValue('--ds-marker-size')) || 24;
  var markerEdgeInset = parseFloat(rootStyle.getPropertyValue('--ds-marker-edge-inset')) || 2;
  var overlayStart = parseFloat(rootStyle.getPropertyValue('--ds-layer-overlay-start')) || 200000;
  var overlayStep = parseFloat(rootStyle.getPropertyValue('--ds-layer-overlay-step')) || 2000;
  var overlayMarkerOffset = parseFloat(rootStyle.getPropertyValue('--ds-layer-overlay-marker-offset')) || 1000;
  var ownsSpacePan = false;

  if (inFrame) document.body.classList.add('ds-in-frame');

  function envelope(type, payload) {
    var result = {
      channel: CHANNEL,
      protocolVersion: PROTOCOL_VERSION,
      type: type,
      pageId: manifest.pageId
    };
    Object.keys(payload || {}).forEach(function (key) { result[key] = payload[key]; });
    return result;
  }

  function send(type, payload) {
    if (inFrame) window.parent.postMessage(envelope(type, payload), '*');
  }

  function validParentMessage(event, data) {
    return event.source === window.parent && data && data.channel === CHANNEL &&
      data.protocolVersion === PROTOCOL_VERSION && data.pageId === manifest.pageId;
  }

  function isTypingTarget(target) {
    if (!target || target === document.body || target === document.documentElement) return false;
    return Boolean(target.closest && target.closest('input,textarea,select,[contenteditable="true"],[role="textbox"],[role="combobox"]'));
  }

  function isSpaceEvent(event) {
    return (event.code === 'Space' || event.key === ' ') && !event.ctrlKey && !event.metaKey && !event.altKey;
  }

  function startSpacePan(event) {
    if (!inFrame || !isSpaceEvent(event) || isTypingTarget(event.target)) return;
    event.preventDefault();
    if (ownsSpacePan || event.repeat) return;
    ownsSpacePan = true;
    send('space-pan-start');
  }

  function endSpacePan(event) {
    if (!ownsSpacePan || (event && !isSpaceEvent(event))) return;
    if (event) event.preventDefault();
    ownsSpacePan = false;
    send('space-pan-end');
  }

  function pixelDelta(value, deltaMode, axis) {
    if (deltaMode === 1) return value * 16;
    if (deltaMode === 2) return value * (axis === 'x' ? window.innerWidth : window.innerHeight);
    return value;
  }

  function consumesAxis(element, axis) {
    if (!element || !element.getAttribute) return false;
    var declaration = element.getAttribute('data-ds-scroll-consumer');
    return declaration === 'both' || declaration === axis;
  }

  function hasScrollableOverflow(element, axis) {
    if (!consumesAxis(element, axis)) return false;
    var style = getComputedStyle(element);
    var overflow = axis === 'x' ? style.overflowX : style.overflowY;
    if (!/(auto|scroll|overlay)/.test(overflow)) return false;
    var clientSize = axis === 'x' ? element.clientWidth : element.clientHeight;
    var scrollSize = axis === 'x' ? element.scrollWidth : element.scrollHeight;
    return scrollSize > clientSize + 1;
  }

  function exclusiveScrollConsumerFor(target) {
    var element = target && target.nodeType === 1 ? target : target && target.parentElement;
    while (element && element !== document.documentElement) {
      var consumesX = hasScrollableOverflow(element, 'x');
      var consumesY = hasScrollableOverflow(element, 'y');
      if (consumesX || consumesY) {
        return { element: element, x: consumesX, y: consumesY };
      }
      element = element.parentElement;
    }
    return null;
  }

  function handleTrackpadPan(event) {
    if (!inFrame || event.ctrlKey || event.metaKey || (!event.deltaX && !event.deltaY)) return;
    var pixelX = pixelDelta(event.deltaX, event.deltaMode, 'x');
    var pixelY = pixelDelta(event.deltaY, event.deltaMode, 'y');
    if (Math.abs(pixelX) < 1) pixelX = 0;
    var scrollConsumer = exclusiveScrollConsumerFor(event.target);
    if (scrollConsumer) {
      event.preventDefault();
      if (scrollConsumer.x && pixelX) scrollConsumer.element.scrollLeft += pixelX;
      if (scrollConsumer.y && pixelY) scrollConsumer.element.scrollTop += pixelY;
      return;
    }
    event.preventDefault();
    send('canvas-pan', {
      deltaX: pixelX ? event.deltaX : 0,
      deltaY: event.deltaY,
      deltaMode: event.deltaMode
    });
  }

  function anchorFor(key) {
    var escaped = String(key).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    return document.querySelector('[data-ds-spec-anchor="' + escaped + '"]');
  }

  function isVisible(element) {
    if (!element || !element.isConnected) return false;
    var style = getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    var rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function hasCurrentChange(value) {
    if (!value || typeof value !== 'object') return false;
    if (value.changeType === 'new' || value.changeType === 'modified') return true;
    return Object.keys(value).some(function (key) {
      var child = value[key];
      if (Array.isArray(child)) return child.some(hasCurrentChange);
      return child && typeof child === 'object' ? hasCurrentChange(child) : false;
    });
  }

  function markerStatus(moduleSpec) {
    if (moduleSpec.changeType === 'new' || moduleSpec.changeType === 'modified') return moduleSpec.changeType;
    return hasCurrentChange(moduleSpec) ? 'modified' : 'existing';
  }

  function emitContentSize() {
    if (!root || !document.body || !document.documentElement) return;
    var bodyStyle = getComputedStyle(document.body);
    var bottomPadding = parseFloat(bodyStyle.paddingBottom) || 0;
    var rootRect = root.getBoundingClientRect();
    var width = Math.ceil(Math.max(document.body.scrollWidth, document.documentElement.scrollWidth, root.scrollWidth || 0));
    var height = Math.ceil(Math.max(rootRect.bottom + window.scrollY + bottomPadding, root.scrollHeight || 0, document.body.scrollHeight));
    send('content-size', { width: width, height: height });
  }

  function reportContentSize() {
    cancelAnimationFrame(sizeFrame);
    emitContentSize();
    sizeFrame = requestAnimationFrame(emitContentSize);
  }

  function clampMarkerCoordinate(value, minimum, maximum) {
    if (maximum < minimum) return minimum;
    return Math.min(Math.max(value, minimum), maximum);
  }

  function ensureOverlayLayer(depth, overlayZ) {
    if (overlayLayers[depth] && overlayLayers[depth].isConnected) {
      overlayLayers[depth].style.setProperty('--ds-overlay-marker-z', String(overlayZ + overlayMarkerOffset));
      return overlayLayers[depth];
    }
    var layer = document.createElement('div');
    layer.className = 'ds-spec-marker-layer ds-overlay';
    layer.dataset.pdOverlayMarkerDepth = String(depth);
    layer.setAttribute('aria-label', '第 ' + depth + ' 层浮层技术规范标注');
    layer.style.setProperty('--ds-overlay-marker-z', String(overlayZ + overlayMarkerOffset));
    overlayMarkerHost.appendChild(layer);
    overlayLayers[depth] = layer;
    return layer;
  }

  function syncOverlayStack() {
    managedOverlayRoots.forEach(function (overlayRoot) {
      overlayRoot.classList.remove('ds-overlay-managed');
      overlayRoot.style.removeProperty('--ds-overlay-z');
      delete overlayRoot.dataset.pdOverlayDepth;
    });
    managedOverlayRoots = Array.prototype.filter.call(
      document.querySelectorAll('[data-ds-overlay-root]'),
      isVisible
    );
    topBlockingOverlayDepth = 0;
    managedOverlayRoots.forEach(function (overlayRoot, index) {
      var depth = index + 1;
      var overlayZ = overlayStart + (depth - 1) * overlayStep;
      overlayRoot.classList.add('ds-overlay-managed');
      overlayRoot.dataset.pdOverlayDepth = String(depth);
      overlayRoot.style.setProperty('--ds-overlay-z', String(overlayZ));
      ensureOverlayLayer(depth, overlayZ);
      if (overlayRoot.getAttribute('data-ds-overlay-mode') !== 'nonmodal') {
        topBlockingOverlayDepth = depth;
      }
    });
    baseLayer.classList.toggle('ds-suppressed', topBlockingOverlayDepth > 0);
    Object.keys(overlayLayers).forEach(function (depthKey) {
      var depth = Number(depthKey);
      var active = depth <= managedOverlayRoots.length;
      overlayLayers[depth].classList.toggle(
        'ds-suppressed',
        !active || depth < topBlockingOverlayDepth
      );
    });
  }

  function markerLayerFor(anchor, moduleSpec) {
    var overlayRoot = anchor.closest && anchor.closest('[data-ds-overlay-root]');
    if (overlayRoot && overlayRoot.dataset.pdOverlayDepth) {
      var depth = Number(overlayRoot.dataset.pdOverlayDepth);
      return { layer: overlayLayers[depth], depth: depth };
    }
    if (moduleSpec.layer === 'modal') return null;
    return { layer: baseLayer, depth: 0 };
  }

  function positionMarkers() {
    cancelAnimationFrame(markerFrame);
    markerFrame = requestAnimationFrame(function () {
      syncOverlayStack();
      var viewportLeft = window.scrollX;
      var viewportTop = window.scrollY;
      var viewportWidth = document.documentElement.clientWidth || window.innerWidth;
      var viewportHeight = document.documentElement.clientHeight || window.innerHeight;
      var minimumLeft = viewportLeft + markerEdgeInset;
      var minimumTop = viewportTop + markerEdgeInset;
      var maximumLeft = viewportLeft + viewportWidth - markerSize - markerEdgeInset;
      var maximumTop = viewportTop + viewportHeight - markerSize - markerEdgeInset;
      markerRecords.forEach(function (record) {
        var anchor = anchorFor(record.spec.key);
        if (!isVisible(anchor)) {
          record.dot.classList.remove('ds-visible');
          return;
        }
        var layerRecord = markerLayerFor(anchor, record.spec);
        if (!layerRecord || layerRecord.depth < topBlockingOverlayDepth) {
          record.dot.classList.remove('ds-visible');
          return;
        }
        if (record.dot.parentElement !== layerRecord.layer) layerRecord.layer.appendChild(record.dot);
        var rect = anchor.getBoundingClientRect();
        var idealLeft = rect.right + viewportLeft - markerSize / 2;
        var idealTop = rect.top + viewportTop - markerSize / 2;
        var left = clampMarkerCoordinate(idealLeft, minimumLeft, maximumLeft);
        var top = clampMarkerCoordinate(idealTop, minimumTop, maximumTop);
        record.dot.style.left = left + 'px';
        record.dot.style.top = top + 'px';
        record.dot.classList.add('ds-visible');
      });
    });
  }

  function mountMarkers() {
    var specs = manifest.specs || {};
    if (specs.enabled === false) return;
    (specs.modules || []).forEach(function (moduleSpec, index) {
      var dot = document.createElement('button');
      var status = markerStatus(moduleSpec);
      dot.type = 'button';
      dot.className = 'ds-spec-marker ds-' + status;
      dot.textContent = String(index + 1);
      dot.title = (index + 1) + ' ' + (moduleSpec.title || '模块技术规范');
      dot.setAttribute('aria-label', dot.title);
      dot.addEventListener('click', function () { send('spec-module-selected', { moduleKey: moduleSpec.key }); });
      baseLayer.appendChild(dot);
      markerRecords.push({ spec: moduleSpec, dot: dot });
    });
    positionMarkers();
  }

  function applyViewport(viewport) {
    if (!viewport || !viewport.type) return;
    document.documentElement.dataset.pdViewport = viewport.type;
    document.documentElement.style.setProperty('--ds-viewport-width', Number(viewport.width) + 'px');
    document.documentElement.style.setProperty('--ds-viewport-height', Number(viewport.height) + 'px');
    window.dispatchEvent(new CustomEvent('prototype:viewportchange', { detail: viewport }));
    positionMarkers();
    reportContentSize();
    send('viewport-applied', { viewport: viewport });
  }

  window.addEventListener('message', function (event) {
    var data = event.data;
    if (!validParentMessage(event, data)) return;
    if (data.type === 'set-viewport') applyViewport(data.viewport);
    else if (data.type === 'space-pan-reset') ownsSpacePan = false;
  });
  window.addEventListener('keydown', startSpacePan, true);
  window.addEventListener('keyup', endSpacePan, true);
  window.addEventListener('wheel', handleTrackpadPan, { passive: false, capture: true });
  document.addEventListener('visibilitychange', function () { if (document.hidden) endSpacePan(); });

  var defaultViewport = manifest.viewports && (manifest.viewports.supported || []).find(function (item) {
    return item.type === manifest.viewports.default;
  });
  if (defaultViewport) applyViewport(defaultViewport);

  mountMarkers();
  send('page-ready', { manifest: manifest });
  window.addEventListener('load', function () { positionMarkers(); reportContentSize(); });
  window.addEventListener('resize', function () { positionMarkers(); reportContentSize(); });
  window.addEventListener('scroll', positionMarkers, true);

  if (window.ResizeObserver) {
    var resizeObserver = new ResizeObserver(function () { positionMarkers(); reportContentSize(); });
    resizeObserver.observe(root);
    resizeObserver.observe(document.body);
  }
  if (window.MutationObserver) {
    var mutationObserver = new MutationObserver(function () {
      positionMarkers();
      reportContentSize();
    });
    mutationObserver.observe(root, { childList: true, subtree: true, attributes: true });
  }
  var layoutPoll = window.setInterval(function () {
    positionMarkers();
    emitContentSize();
  }, 250);
  window.addEventListener('beforeunload', function () { endSpacePan(); window.clearInterval(layoutPoll); });

  var backButton = document.getElementById('pdBackToFrame');
  if (backButton) backButton.addEventListener('click', function () {
    var file = decodeURIComponent(location.pathname.split('/').pop() || location.href.split('/').pop());
    location.href = 'index.html#page=' + encodeURIComponent(file);
  });
  reportContentSize();
})();
