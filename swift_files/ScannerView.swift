import SwiftUI
import AVFoundation

struct ScannerView: UIViewControllerRepresentable {
    let onFound: (String) -> Void
    let onCancel: () -> Void
    let onError: (String) -> Void

    func makeUIViewController(context: Context) -> ScannerVC {
        let vc = ScannerVC()
        vc.onFound = onFound
        vc.onCancel = onCancel
        vc.onError  = onError
        return vc
    }
    func updateUIViewController(_ uiViewController: ScannerVC, context: Context) {}
}

final class ScannerVC: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var onFound: ((String) -> Void)?
    var onCancel: (() -> Void)?
    var onError: ((String) -> Void)?

    private let session = AVCaptureSession()
    private var previewLayer: AVCaptureVideoPreviewLayer?
    private let feedback = UINotificationFeedbackGenerator()
    private var isHandling = false
    private var torchButton: UIButton?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        configureCamera()
        configureOverlay()
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        if !session.isRunning { session.startRunning() }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        if session.isRunning { session.stopRunning() }
    }

    private func configureCamera() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            setUpSession()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { granted in
                DispatchQueue.main.async {
                    if granted { self.setUpSession() }
                    else { self.onCancel?(); self.dismiss(animated: true) }
                }
            }
        default:
            onError?("Camera permission denied.")
            dismiss(animated: true)
        }
    }

    private func setUpSession() {
        session.beginConfiguration()
        session.sessionPreset = .high

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input) else {
            session.commitConfiguration()
            onError?("No camera available.")
            dismiss(animated: true)
            return
        }
        session.addInput(input)

        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else {
            session.commitConfiguration()
            onError?("Scanner output unavailable.")
            dismiss(animated: true)
            return
        }
        session.addOutput(output)
        output.setMetadataObjectsDelegate(self, queue: .main)
        output.metadataObjectTypes = [
            .qr, .ean13, .ean8, .upce, .code128, .code39, .code93,
            .itf14, .pdf417, .aztec, .dataMatrix, .interleaved2of5
        ]

        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        layer.frame = view.layer.bounds
        view.layer.insertSublayer(layer, at: 0)
        previewLayer = layer

        session.commitConfiguration()
        session.startRunning()
    }

    private func configureOverlay() {
        let guide = UIView()
        guide.layer.borderColor = UIColor.white.withAlphaComponent(0.9).cgColor
        guide.layer.borderWidth = 2
        guide.layer.cornerRadius = 12
        guide.translatesAutoresizingMaskIntoConstraints = false

        let dim = UIView()
        dim.backgroundColor = UIColor.black.withAlphaComponent(0.25)
        dim.translatesAutoresizingMaskIntoConstraints = false

        let label = UILabel()
        label.text = "Align barcode within the box"
        label.textColor = .white
        label.font = .systemFont(ofSize: 15, weight: .medium)
        label.translatesAutoresizingMaskIntoConstraints = false

        let close = UIButton(type: .system)
        close.setTitle("Close", for: .normal)
        close.setTitleColor(.white, for: .normal)
        close.titleLabel?.font = .systemFont(ofSize: 17, weight: .semibold)
        close.translatesAutoresizingMaskIntoConstraints = false
        close.addTarget(self, action: #selector(closeTapped), for: .touchUpInside)

        let torch = UIButton(type: .system)
        torch.setTitle("Torch", for: .normal)
        torch.setTitleColor(.white, for: .normal)
        torch.titleLabel?.font = .systemFont(ofSize: 17, weight: .semibold)
        torch.translatesAutoresizingMaskIntoConstraints = false
        torch.addTarget(self, action: #selector(torchTapped), for: .touchUpInside)
        torchButton = torch

        [dim, guide, label, close, torch].forEach { view.addSubview($0) }

        NSLayoutConstraint.activate([
            dim.topAnchor.constraint(equalTo: view.topAnchor),
            dim.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            dim.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            dim.trailingAnchor.constraint(equalTo: view.trailingAnchor),

            guide.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            guide.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            guide.widthAnchor.constraint(equalTo: view.widthAnchor, multiplier: 0.75),
            guide.heightAnchor.constraint(equalTo: guide.widthAnchor, multiplier: 0.5),

            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.topAnchor.constraint(equalTo: guide.bottomAnchor, constant: 16),

            close.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            close.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 8),

            torch.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
            torch.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 8),
        ])
    }

    @objc private func closeTapped() {
        onCancel?()
        dismiss(animated: true)
    }

    @objc private func torchTapped() {
        guard let device = AVCaptureDevice.default(for: .video), device.hasTorch else { return }
        do {
            try device.lockForConfiguration()
            device.torchMode = device.torchMode == .on ? .off : .on
            try device.setTorchModeOn(level: AVCaptureDevice.maxAvailableTorchLevel)
            device.unlockForConfiguration()
        } catch {
            // ignore; torch may be unavailable
        }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput,
                        didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        guard !isHandling,
              let obj = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              let raw = obj.stringValue, !raw.isEmpty else { return }

        isHandling = true
        feedback.notificationOccurred(.success)
        session.stopRunning()

        let normalized: String
        if obj.type == .ean13, raw.count == 13, raw.hasPrefix("0") {
            normalized = String(raw.dropFirst()) // EAN-13 with leading 0 → UPC-A
        } else {
            normalized = raw
        }

        dismiss(animated: true) { [weak self] in self?.onFound?(normalized) }
    }
}
