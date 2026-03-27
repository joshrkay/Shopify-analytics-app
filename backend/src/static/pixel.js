/**
 * MarkInsight Web Pixel — Shopify Customer Event Tracker
 *
 * This script runs in Shopify's sandboxed web pixel environment.
 * It subscribes to standard customer events and sends them to the
 * MarkInsight backend for attribution and funnel analysis.
 *
 * Events tracked:
 * - page_viewed: All page views with URL and referrer
 * - product_viewed: Product detail page views
 * - collection_viewed: Collection/category page views
 * - search_submitted: Search queries
 * - cart_viewed: Cart page views
 * - checkout_started: Checkout initiation
 * - checkout_completed: Purchase confirmation
 * - payment_info_submitted: Payment step completion
 *
 * Privacy: No PII is collected. Session IDs are anonymous UUIDs.
 * UTM parameters are extracted from the landing page URL only.
 */

(function () {
  // Parse pixel settings (injected by Shopify from webPixelCreate)
  const settings = JSON.parse(
    typeof init !== "undefined" && init.settings ? init.settings : "{}"
  );
  const ENDPOINT_URL = settings.endpoint_url || "";
  const SHOP_DOMAIN = settings.shop_domain || "";

  if (!ENDPOINT_URL) {
    return; // No endpoint configured — pixel is inactive
  }

  // Generate anonymous session ID
  function generateSessionId() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  var sessionId = generateSessionId();
  var eventBuffer = [];
  var flushTimer = null;
  var utmParams = {};
  var utmExtracted = false;

  // Extract UTM parameters from URL
  function extractUtmParams(url) {
    if (utmExtracted) return;
    try {
      var searchParams = new URL(url).searchParams;
      var fields = [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
      ];
      fields.forEach(function (field) {
        var val = searchParams.get(field);
        if (val) utmParams[field] = val;
      });
      utmExtracted = true;
    } catch (e) {
      // URL parsing failed — skip UTM extraction
    }
  }

  // Buffer an event for batched sending
  function trackEvent(eventType, eventData, pageUrl, referrer) {
    eventBuffer.push({
      event_type: eventType,
      event_data: eventData || {},
      page_url: pageUrl || "",
      referrer: referrer || "",
      utm_source: utmParams.utm_source || null,
      utm_medium: utmParams.utm_medium || null,
      utm_campaign: utmParams.utm_campaign || null,
      utm_term: utmParams.utm_term || null,
      utm_content: utmParams.utm_content || null,
      event_timestamp: new Date().toISOString(),
    });

    // Flush after 5 events or 3 seconds, whichever comes first
    if (eventBuffer.length >= 5) {
      flushEvents();
    } else if (!flushTimer) {
      flushTimer = setTimeout(flushEvents, 3000);
    }
  }

  // Send buffered events to backend
  function flushEvents() {
    if (flushTimer) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }

    if (eventBuffer.length === 0) return;

    var events = eventBuffer.slice();
    eventBuffer = [];

    var payload = {
      shop_domain: SHOP_DOMAIN,
      session_id: sessionId,
      events: events,
    };

    try {
      fetch(ENDPOINT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true, // Ensure delivery even on page unload
      }).catch(function () {
        // Silently fail — pixel should never break the store
      });
    } catch (e) {
      // Silently fail
    }
  }

  // Extract context helpers
  function getPageUrl(event) {
    try {
      return (
        (event.context && event.context.document && event.context.document.location && event.context.document.location.href) ||
        (event.context && event.context.window && event.context.window.location && event.context.window.location.href) ||
        ""
      );
    } catch (e) {
      return "";
    }
  }

  function getReferrer(event) {
    try {
      return (
        (event.context && event.context.document && event.context.document.referrer) || ""
      );
    } catch (e) {
      return "";
    }
  }

  // Subscribe to standard Shopify customer events
  analytics.subscribe("page_viewed", function (event) {
    var url = getPageUrl(event);
    extractUtmParams(url);
    trackEvent("page_viewed", {}, url, getReferrer(event));
  });

  analytics.subscribe("product_viewed", function (event) {
    var url = getPageUrl(event);
    extractUtmParams(url);
    var productData = {};
    if (event.data && event.data.productVariant) {
      var pv = event.data.productVariant;
      productData = {
        product_id: pv.product && pv.product.id,
        product_title: pv.product && pv.product.title,
        variant_id: pv.id,
        variant_title: pv.title,
        price: pv.price && pv.price.amount,
        currency: pv.price && pv.price.currencyCode,
      };
    }
    trackEvent("product_viewed", productData, url, getReferrer(event));
  });

  analytics.subscribe("collection_viewed", function (event) {
    var url = getPageUrl(event);
    extractUtmParams(url);
    var collectionData = {};
    if (event.data && event.data.collection) {
      collectionData = {
        collection_id: event.data.collection.id,
        collection_title: event.data.collection.title,
      };
    }
    trackEvent("collection_viewed", collectionData, url, getReferrer(event));
  });

  analytics.subscribe("search_submitted", function (event) {
    var url = getPageUrl(event);
    extractUtmParams(url);
    var searchData = {};
    if (event.data && event.data.searchResult) {
      searchData = {
        query: event.data.searchResult.query,
      };
    }
    trackEvent("search_submitted", searchData, url, getReferrer(event));
  });

  analytics.subscribe("cart_viewed", function (event) {
    var url = getPageUrl(event);
    trackEvent("cart_viewed", {}, url, getReferrer(event));
  });

  analytics.subscribe("checkout_started", function (event) {
    var url = getPageUrl(event);
    var checkoutData = {};
    if (event.data && event.data.checkout) {
      checkoutData = {
        token: event.data.checkout.token,
        total_price: event.data.checkout.totalPrice && event.data.checkout.totalPrice.amount,
        currency: event.data.checkout.currencyCode,
        line_items_count:
          event.data.checkout.lineItems && event.data.checkout.lineItems.length,
      };
    }
    trackEvent("checkout_started", checkoutData, url, getReferrer(event));
  });

  analytics.subscribe("payment_info_submitted", function (event) {
    var url = getPageUrl(event);
    trackEvent("payment_info_submitted", {}, url, getReferrer(event));
  });

  analytics.subscribe("checkout_completed", function (event) {
    var url = getPageUrl(event);
    var purchaseData = {};
    if (event.data && event.data.checkout) {
      var checkout = event.data.checkout;
      purchaseData = {
        order_id: checkout.order && checkout.order.id,
        token: checkout.token,
        total_price: checkout.totalPrice && checkout.totalPrice.amount,
        subtotal_price: checkout.subtotalPrice && checkout.subtotalPrice.amount,
        currency: checkout.currencyCode,
        line_items_count: checkout.lineItems && checkout.lineItems.length,
      };
    }
    trackEvent("checkout_completed", purchaseData, url, getReferrer(event));

    // Flush immediately on purchase — critical event
    flushEvents();
  });
})();
