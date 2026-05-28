"""
Stripe Checkout Page — In-app payment form using QWebEngineView + Stripe.js.

Renders the Stripe Payment Element as a page in the library stack. Handles:
- New card entry
- Saved payment methods (one-click pay for returning customers)
- Success/error communication back to Python via QWebChannel
"""

from pathlib import Path
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel


# -- Colour tokens (match picker dark theme) --
_BG = "#1d1d1d"
_TEXT_PRIMARY = "#e0e0e0"
_TEXT_SECONDARY = "#999999"
_ACCENT_BLUE = "#1D65CA"


class _StripeBridge(QtCore.QObject):
    """JavaScript <-> Python bridge via QWebChannel."""

    payment_success = QtCore.Signal(str)   # payment_intent_id
    payment_error = QtCore.Signal(str)     # error message
    payment_cancelled = QtCore.Signal()
    ready = QtCore.Signal()                # Stripe Elements mounted

    @QtCore.Slot(str)
    def onPaymentSuccess(self, payment_intent_id):
        self.payment_success.emit(payment_intent_id)

    @QtCore.Slot(str)
    def onPaymentError(self, message):
        self.payment_error.emit(message)

    @QtCore.Slot()
    def onCancel(self):
        self.payment_cancelled.emit()

    @QtCore.Slot()
    def onReady(self):
        self.ready.emit()


def _build_checkout_html(
    publishable_key: str,
    client_secret: str,
    customer_session_secret: str,
    product_name: str,
    price_display: str,
) -> str:
    """Return the HTML page that hosts Stripe Payment Element."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://js.stripe.com/v3/"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: transparent;
    color: {_TEXT_PRIMARY};
    padding: 16px;
    min-height: 100vh;
  }}

  /* ---- Scrollbar (match addon 6px thin style) ---- */
  ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: rgba(100,100,100,0.4); border-radius: 3px; }}
  ::-webkit-scrollbar-thumb:hover {{ background: rgba(120,120,120,0.7); }}

  .header {{
    text-align: center;
    margin-bottom: 16px;
    padding-top: 4px;
  }}
  .header h2 {{
    font-size: 13px;
    font-weight: 600;
    color: {_TEXT_SECONDARY};
    margin-bottom: 4px;
  }}
  .header .price {{
    font-size: 20px;
    font-weight: 700;
    color: {_TEXT_PRIMARY};
  }}
  #payment-element {{
    margin-bottom: 14px;
  }}
  #submit-btn {{
    width: 100%;
    padding: 10px;
    border: none;
    border-radius: 6px;
    background: {_ACCENT_BLUE};
    color: white;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
  }}
  #submit-btn:hover {{ background: #2570d4; }}
  #submit-btn:disabled {{
    background: #444;
    cursor: not-allowed;
  }}
  #cancel-btn {{
    width: 100%;
    padding: 8px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #666;
    font-size: 12px;
    cursor: pointer;
    margin-top: 6px;
  }}
  #cancel-btn:hover {{ color: #999; }}
  #error-msg {{
    color: #ff6b6b;
    font-size: 12px;
    text-align: center;
    margin-top: 6px;
    min-height: 16px;
  }}
  .spinner {{
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
    vertical-align: middle;
    margin-right: 5px;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .loading-overlay {{
    position: fixed;
    inset: 0;
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }}
  .loading-overlay .spinner {{
    width: 24px;
    height: 24px;
    border-width: 3px;
  }}
</style>
</head>
<body>
  <div id="loading" class="loading-overlay"><div class="spinner"></div></div>

  <div class="header">
    <h2>{_html_escape(product_name)}</h2>
    <div class="price">{_html_escape(price_display)}</div>
  </div>

  <form id="payment-form">
    <div id="payment-element"></div>
    <div id="error-msg"></div>
    <button id="submit-btn" type="submit" disabled>
      Pay {_html_escape(price_display)}
    </button>
    <button id="cancel-btn" type="button">Cancel</button>
  </form>

<script>
(function() {{
  let bridge = null;
  const stripe = Stripe('{publishable_key}');
  const elements = stripe.elements({{
    clientSecret: '{client_secret}',
    customerSessionClientSecret: '{customer_session_secret}',
    appearance: {{
      theme: 'night',
      variables: {{
        colorPrimary: '{_ACCENT_BLUE}',
        colorBackground: '#2a2a2a',
        colorText: '{_TEXT_PRIMARY}',
        colorDanger: '#ff6b6b',
        borderRadius: '4px',
        fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
        fontSizeBase: '13px',
      }},
      rules: {{
        '.Input': {{
          border: '1px solid #3a3a3a',
          backgroundColor: 'rgba(50, 50, 50, 0.8)',
          fontSize: '13px',
          padding: '8px',
        }},
        '.Input:focus': {{
          border: '1px solid {_ACCENT_BLUE}',
          boxShadow: 'none',
        }},
        '.Label': {{
          fontSize: '12px',
          color: '{_TEXT_SECONDARY}',
        }},
      }},
    }},
  }});

  const paymentElement = elements.create('payment');
  paymentElement.mount('#payment-element');

  paymentElement.on('ready', function() {{
    document.getElementById('loading').style.display = 'none';
    document.getElementById('submit-btn').disabled = false;
    if (bridge) bridge.onReady();
  }});

  new QWebChannel(qt.webChannelTransport, function(channel) {{
    bridge = channel.objects.bridge;
  }});

  const form = document.getElementById('payment-form');
  const submitBtn = document.getElementById('submit-btn');
  const errorMsg = document.getElementById('error-msg');

  form.addEventListener('submit', async function(e) {{
    e.preventDefault();
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Processing...';
    errorMsg.textContent = '';

    const {{ error, paymentIntent }} = await stripe.confirmPayment({{
      elements,
      redirect: 'if_required',
      confirmParams: {{
        return_url: 'https://localhost/payment/complete',
      }},
    }});

    if (error) {{
      errorMsg.textContent = error.message || 'Payment failed';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Pay {_html_escape(price_display)}';
      if (bridge) bridge.onPaymentError(error.message || 'Payment failed');
    }} else if (paymentIntent && paymentIntent.status === 'succeeded') {{
      submitBtn.innerHTML = '&#10003; Payment Successful';
      submitBtn.style.background = '#2ea043';
      if (bridge) bridge.onPaymentSuccess(paymentIntent.id);
    }} else {{
      errorMsg.textContent = 'Unexpected status: ' + (paymentIntent?.status || 'unknown');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Pay {_html_escape(price_display)}';
    }}
  }});

  document.getElementById('cancel-btn').addEventListener('click', function() {{
    if (bridge) bridge.onCancel();
  }});
}})();
</script>
</body>
</html>"""


def _html_escape(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


class StripeCheckoutPage(QtWidgets.QWidget):
    """
    Embedded checkout page that renders Stripe Payment Element in a QWebEngineView.

    Used as a page in the library outer stack — same pattern as ProductDetailPage.

    Signals
    -------
    back_requested()
        Emitted when the user clicks the back arrow or cancels.
    payment_success(str)
        Emitted with the payment_intent_id when payment succeeds.
    payment_error(str)
        Emitted with the error message on failure.
    payment_cancelled()
        Emitted when the user clicks Cancel or navigates back.
    """

    back_requested = QtCore.Signal()
    payment_success = QtCore.Signal(str)
    payment_error = QtCore.Signal(str)
    payment_cancelled = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = None
        self._webview = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- Toolbar (matches ProductDetailPage) ----
        toolbar = QtWidgets.QWidget()
        toolbar.setFixedHeight(32)
        toolbar.setStyleSheet("background: transparent;")
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(6)

        self._back_btn = QtWidgets.QPushButton()
        self._back_btn.setFixedSize(24, 24)
        self._back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        _arrow_path = Path(__file__).parent / "bgen_picker_icons" / "arrow_left_icon.png"
        if _arrow_path.exists():
            self._back_btn.setIcon(QtGui.QIcon(QtGui.QPixmap(str(_arrow_path))))
            self._back_btn.setIconSize(QtCore.QSize(14, 14))
        else:
            self._back_btn.setText("<")
        self._back_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.08); "
            "border: none; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )
        self._back_btn.clicked.connect(self._on_back)
        toolbar_layout.addWidget(self._back_btn)

        self._toolbar_title = QtWidgets.QLabel("Checkout")
        self._toolbar_title.setStyleSheet(
            "color: #cccccc; font-size: 12px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        toolbar_layout.addWidget(self._toolbar_title)
        toolbar_layout.addStretch()
        main_layout.addWidget(toolbar)

        # ---- WebView ----
        self._webview = QWebEngineView()
        self._webview.setStyleSheet("background: transparent;")
        main_layout.addWidget(self._webview)

    def load_checkout(
        self,
        publishable_key: str,
        client_secret: str,
        customer_session_secret: str,
        product_name: str,
        price_cents: int,
    ):
        """Load a new checkout session into the page."""
        price_display = f"${price_cents / 100:.2f}"
        self._toolbar_title.setText(f"Checkout — {product_name}")

        # Off-the-record profile so no persistent cookies leak
        profile = QWebEngineProfile(self)
        page = QWebEnginePage(profile, self)
        page.setBackgroundColor(QtGui.QColor(0, 0, 0, 0))
        self._webview.setPage(page)

        # Set up QWebChannel bridge
        self._bridge = _StripeBridge(self)
        self._bridge.payment_success.connect(self._on_success)
        self._bridge.payment_error.connect(self._on_error)
        self._bridge.payment_cancelled.connect(self._on_cancel)

        channel = QWebChannel(page)
        channel.registerObject("bridge", self._bridge)
        page.setWebChannel(channel)

        html = _build_checkout_html(
            publishable_key=publishable_key,
            client_secret=client_secret,
            customer_session_secret=customer_session_secret,
            product_name=product_name,
            price_display=price_display,
        )
        page.setHtml(html, QtCore.QUrl("https://checkout.stripe.local"))

    def _on_back(self):
        self.payment_cancelled.emit()
        self.back_requested.emit()

    def _on_success(self, payment_intent_id: str):
        self.payment_success.emit(payment_intent_id)
        # Brief delay so user sees "Payment Successful", then navigate back
        QtCore.QTimer.singleShot(800, self.back_requested.emit)

    def _on_error(self, message: str):
        self.payment_error.emit(message)
        # Don't navigate back — let the user retry or cancel

    def _on_cancel(self):
        self.payment_cancelled.emit()
        self.back_requested.emit()
