import SwiftUI
import WebKit

final class BarcodeBridge: NSObject, WKScriptMessageHandler {
    private let onBarcodeBridge: (_ action: String, _ source: String?) -> Void
    private let onConsoleLog: (String) -> Void

    init(onBarcodeBridge: @escaping (_ action: String, _ source: String?) -> Void,
         onConsoleLog: @escaping (String) -> Void) {
        self.onBarcodeBridge = onBarcodeBridge
        self.onConsoleLog = onConsoleLog
        super.init()
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.name == "barcodeScanner" {
            // Expect { action: 'start'|'stop', source?: 'hardware-form' } from web app
            var action = ""
            var source: String?
            if let dict = message.body as? [String: Any] {
                action = (dict["action"] as? String) ?? ""
                source = dict["source"] as? String
            } else if let s = message.body as? String {
                action = s
            }
            onBarcodeBridge(action, source)
            return
        }

        if message.name == "log" {
            onConsoleLog(String(describing: message.body))
        }
    }
}

struct WebView: UIViewRepresentable {
    let url: URL
    let onBarcodeBridge: (_ action: String, _ source: String?) -> Void
    let onConsoleLog: (String) -> Void
    let onReady: (WKWebView) -> Void

    func makeUIView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()

        // Bridge for barcode + logs
        let bridge = BarcodeBridge(onBarcodeBridge: onBarcodeBridge, onConsoleLog: onConsoleLog)
        contentController.add(bridge, name: "barcodeScanner")  // << the name your page checks
        contentController.add(bridge, name: "log")

        // console.log → native
        let consolePatch = """
        (function() {
          const _log = console.log;
          console.log = function(...args) {
            try { window.webkit.messageHandlers.log.postMessage(args.join(' ')); } catch(e) {}
            _log.apply(console, args);
          };
        })();
        """
        contentController.addUserScript(WKUserScript(source: consolePatch, injectionTime: .atDocumentStart, forMainFrameOnly: false))

        let config = WKWebViewConfiguration()
        config.userContentController = contentController
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.navigationDelegate = context.coordinator

        webView.load(URLRequest(url: url))
        onReady(webView)
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator: NSObject, WKNavigationDelegate {
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            print("[WK] provisional fail:", error.localizedDescription)
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            print("[WK] nav fail:", error.localizedDescription)
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            // Hook for additional JS injections if needed
        }
    }
}
