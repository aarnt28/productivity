import SwiftUI
import WebKit

struct ContentView: View {
    @State private var showScanner = false
    @State private var webViewRef: WKWebView?
    @State private var pendingBridgeSource: String?

    var body: some View {
        ZStack {
            WebView(
                url: URL(string: "https://tracker.turnernet.co")!,
                // Called when JS posts {action:'start'|'stop'} to window.webkit.messageHandlers.barcodeScanner
                onBarcodeBridge: { action, source in
                    switch action {
                    case "start":
                        pendingBridgeSource = source
                        showScanner = true
                    case "stop":
                        // If scanner is open, close it and tell JS it was cancelled (matches your page’s expectations)
                        if showScanner {
                            showScanner = false
                            jsCall("window.appNativeBarcodeScanCancelled()")
                        }
                    default:
                        break
                    }
                },
                // Pipe console.log → Xcode
                onConsoleLog: { print("[JS]", $0) },
                // Keep a reference so we can evaluate JS later
                onReady: { web in webViewRef = web }
            )
        }
        .sheet(isPresented: $showScanner) {
            ScannerView(
                onFound: { value in
                    // Success → tell the webapp
                    let escaped = jsEscape(value)
                    jsCall("window.appNativeBarcodeScanned({ barcode: '\(escaped)' })")
                    showScanner = false
                },
                onCancel: {
                    jsCall("window.appNativeBarcodeScanCancelled()")
                    showScanner = false
                },
                onError: { message in
                    let escaped = jsEscape(message)
                    jsCall("window.appNativeBarcodeScanFailed({ message: '\(escaped)' })")
                    showScanner = false
                }
            )
        }
    }

    private func jsCall(_ script: String) {
        webViewRef?.evaluateJavaScript(script, completionHandler: { result, error in
            if let error = error { print("[JS eval error]", error.localizedDescription) }
        })
    }

    private func jsEscape(_ s: String) -> String {
        s.replacingOccurrences(of: "\\", with: "\\\\")
         .replacingOccurrences(of: "'", with: "\\'")
         .replacingOccurrences(of: "\n", with: "\\n")
    }
}
