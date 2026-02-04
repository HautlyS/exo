"""
MultipeerConnectivity Manager for iOS Device Discovery and Networking

Handles peer discovery, connection management, and data transfer for exo cluster
communication on iOS devices. Works within App Sandbox restrictions without
requiring special entitlements.

Key Features:
- Automatic local peer discovery (no internet required)
- Works over WiFi and Bluetooth
- Handles connection lifecycle
- Data transfer with automatic fragmentation
"""

import Foundation
import MultipeerConnectivity
import Combine

/// Represents a remote peer in the cluster
@Observable
class PeerInfo: Identifiable {
    let id: String
    let displayName: String
    let peerID: MCPeerID
    
    @ObservationIgnored var state: MCSessionState = .notConnected {
        didSet { objectWillChange.send() }
    }
    
    let objectWillChange = PassthroughSubject<Void, Never>()
    
    init(peerID: MCPeerID, displayName: String) {
        self.id = peerID.displayName
        self.displayName = displayName
        self.peerID = peerID
    }
}

/// MultipeerConnectivity Manager for cluster communication
@MainActor
final class MultipeerConnectivityManager: NSObject, ObservableObject {
    
    // MARK: - Properties
    
    private let serviceName = "exo-cluster"
    private let localPeerID: MCPeerID
    
    @Published private(set) var discoveredPeers: [PeerInfo] = []
    @Published private(set) var connectedPeers: [PeerInfo] = []
    @Published private(set) var isAdvertising = false
    @Published private(set) var isBrowsing = false
    
    private var advertiser: MCNearbyServiceAdvertiser?
    private var browser: MCNearbyServiceBrowser?
    private var session: MCSession?
    
    private var peerMap: [String: PeerInfo] = [:]
    
    // MARK: - Initialization
    
    override init() {
        let deviceName = UIDevice.current.name
        self.localPeerID = MCPeerID(displayName: deviceName)
        super.init()
    }
    
    // MARK: - Advertising (Making this device discoverable)
    
    /// Start advertising this device for peer discovery
    nonisolated func startAdvertising() {
        DispatchQueue.main.async {
            guard !self.isAdvertising else { return }
            
            let advertiser = MCNearbyServiceAdvertiser(
                peer: self.localPeerID,
                discoveryInfo: self.discoveryInfo(),
                serviceType: self.serviceName
            )
            advertiser.delegate = self
            
            advertiser.startAdvertisingPeer()
            self.advertiser = advertiser
            
            Task { @MainActor in
                self.isAdvertising = true
            }
            
            os_log("Started advertising %{public}s", log: .networking, type: .info, self.localPeerID.displayName)
        }
    }
    
    /// Stop advertising this device
    nonisolated func stopAdvertising() {
        DispatchQueue.main.async {
            self.advertiser?.stopAdvertisingPeer()
            self.advertiser = nil
            
            Task { @MainActor in
                self.isAdvertising = false
            }
            
            os_log("Stopped advertising", log: .networking, type: .info)
        }
    }
    
    // MARK: - Browsing (Discovering peers)
    
    /// Start browsing for other devices in cluster
    nonisolated func startBrowsing() {
        DispatchQueue.main.async {
            guard !self.isBrowsing else { return }
            
            // Create session first
            let session = MCSession(peer: self.localPeerID, securityIdentity: nil, encryptionPreference: .required)
            session.delegate = self
            self.session = session
            
            // Create browser
            let browser = MCNearbyServiceBrowser(peer: self.localPeerID, serviceType: self.serviceName)
            browser.delegate = self
            browser.startBrowsingForPeers()
            
            self.browser = browser
            
            Task { @MainActor in
                self.isBrowsing = true
            }
            
            os_log("Started browsing for peers", log: .networking, type: .info)
        }
    }
    
    /// Stop browsing for peers
    nonisolated func stopBrowsing() {
        DispatchQueue.main.async {
            self.browser?.stopBrowsingForPeers()
            self.browser = nil
            
            Task { @MainActor in
                self.isBrowsing = false
            }
            
            os_log("Stopped browsing for peers", log: .networking, type: .info)
        }
    }
    
    /// Accept connection invitation from peer
    nonisolated func acceptInvitation(from peerID: MCPeerID) {
        os_log("Accepting invitation from %{public}s", log: .networking, type: .debug, peerID.displayName)
        // Invitation is accepted implicitly by starting session
    }
    
    /// Decline connection invitation from peer
    nonisolated func declineInvitation(from peerID: MCPeerID) {
        os_log("Declining invitation from %{public}s", log: .networking, type: .debug, peerID.displayName)
        // No-op: session won't be established
    }
    
    // MARK: - Data Transfer
    
    /// Send data to connected peer
    /// - Parameters:
    ///   - data: Data to send
    ///   - peerID: Target peer
    /// - Returns: True if send was successful
    func sendData(_ data: Data, toPeer peerID: MCPeerID) -> Bool {
        guard let session = session else {
            os_log("No active session to send data", log: .networking, type: .error)
            return false
        }
        
        do {
            try session.send(data, toPeers: [peerID], with: .reliable)
            return true
        } catch {
            os_log("Failed to send data: %{public}s", log: .networking, type: .error, error.localizedDescription)
            return false
        }
    }
    
    /// Send data to all connected peers
    func broadcastData(_ data: Data) -> Bool {
        guard let session = session else {
            os_log("No active session to broadcast", log: .networking, type: .error)
            return false
        }
        
        do {
            try session.send(data, toPeers: session.connectedPeers, with: .reliable)
            return true
        } catch {
            os_log("Failed to broadcast data: %{public}s", log: .networking, type: .error, error.localizedDescription)
            return false
        }
    }
    
    // MARK: - Query Methods
    
    /// Get peer by ID
    func getPeer(by peerID: MCPeerID) -> PeerInfo? {
        peerMap[peerID.displayName]
    }
    
    /// Check if peer is connected
    func isConnected(to peerID: MCPeerID) -> Bool {
        session?.connectedPeers.contains(peerID) ?? false
    }
    
    /// Get all connected peer IDs
    var allConnectedPeerIDs: [MCPeerID] {
        session?.connectedPeers ?? []
    }
    
    // MARK: - Private Helpers
    
    private func discoveryInfo() -> [String: String]? {
        return [
            "version": "1.0",
            "platform": "iOS",
            "device": UIDevice.current.name
        ]
    }
    
    private nonisolated func updatePeerConnection(_ peerID: MCPeerID, state: MCSessionState) {
        DispatchQueue.main.async {
            let peerKey = peerID.displayName
            
            if let peer = self.peerMap[peerKey] {
                peer.state = state
                
                // Update connected peers list
                if state == .connected {
                    if !self.connectedPeers.contains(where: { $0.peerID == peerID }) {
                        self.connectedPeers.append(peer)
                    }
                } else {
                    self.connectedPeers.removeAll { $0.peerID == peerID }
                }
            }
            
            let stateString: String
            switch state {
            case .notConnected:
                stateString = "disconnected"
            case .connecting:
                stateString = "connecting"
            case .connected:
                stateString = "connected"
            @unknown default:
                stateString = "unknown"
            }
            
            os_log("Peer %{public}s state changed to %{public}s", log: .networking, type: .debug,
                   peerID.displayName, stateString)
        }
    }
    
    // MARK: - Cleanup
    
    deinit {
        stopAdvertising()
        stopBrowsing()
        session?.disconnect()
    }
}

// MARK: - MCNearbyServiceAdvertiserDelegate

extension MultipeerConnectivityManager: MCNearbyServiceAdvertiserDelegate {
    
    nonisolated func advertiser(_ advertiser: MCNearbyServiceAdvertiser,
                               didReceiveInvitationFromPeer peerID: MCPeerID,
                               withContext context: Data?,
                               invitationHandler: @escaping (Bool, MCSession?) -> Void) {
        
        os_log("Received invitation from %{public}s", log: .networking, type: .info, peerID.displayName)
        
        DispatchQueue.main.async {
            guard let session = self.session else {
                invitationHandler(false, nil)
                return
            }
            
            // Accept invitation
            invitationHandler(true, session)
            
            // Add peer to our map if not already there
            if self.peerMap[peerID.displayName] == nil {
                let peer = PeerInfo(peerID: peerID, displayName: peerID.displayName)
                self.peerMap[peerID.displayName] = peer
                self.discoveredPeers.append(peer)
            }
        }
    }
    
    nonisolated func advertiser(_ advertiser: MCNearbyServiceAdvertiser,
                               didNotStartAdvertisingPeer error: Error) {
        os_log("Failed to start advertising: %{public}s", log: .networking, type: .error,
               error.localizedDescription)
    }
}

// MARK: - MCNearbyServiceBrowserDelegate

extension MultipeerConnectivityManager: MCNearbyServiceBrowserDelegate {
    
    nonisolated func browser(_ browser: MCNearbyServiceBrowser,
                            foundPeer peerID: MCPeerID,
                            withDiscoveryInfo info: [String: String]?) {
        
        os_log("Found peer: %{public}s", log: .networking, type: .info, peerID.displayName)
        
        DispatchQueue.main.async {
            // Add to discovered peers if not already there
            let peerKey = peerID.displayName
            if self.peerMap[peerKey] == nil {
                let peer = PeerInfo(peerID: peerID, displayName: info?["device"] ?? peerID.displayName)
                self.peerMap[peerKey] = peer
                self.discoveredPeers.append(peer)
            }
            
            // Send invitation to connect
            guard let session = self.session else { return }
            browser.invitePeer(peerID, to: session, withContext: nil, timeout: 30)
        }
    }
    
    nonisolated func browser(_ browser: MCNearbyServiceBrowser,
                            lostPeer peerID: MCPeerID) {
        
        os_log("Lost peer: %{public}s", log: .networking, type: .info, peerID.displayName)
        
        DispatchQueue.main.async {
            let peerKey = peerID.displayName
            if let peer = self.peerMap[peerKey] {
                self.discoveredPeers.removeAll { $0.peerID == peerID }
                self.connectedPeers.removeAll { $0.peerID == peerID }
                self.peerMap.removeValue(forKey: peerKey)
            }
        }
    }
    
    nonisolated func browser(_ browser: MCNearbyServiceBrowser,
                            didNotStartBrowsingForPeers error: Error) {
        os_log("Failed to start browsing: %{public}s", log: .networking, type: .error,
               error.localizedDescription)
    }
}

// MARK: - MCSessionDelegate

extension MultipeerConnectivityManager: MCSessionDelegate {
    
    nonisolated func session(_ session: MCSession,
                            peer peerID: MCPeerID,
                            didChange state: MCSessionState) {
        updatePeerConnection(peerID, state: state)
    }
    
    nonisolated func session(_ session: MCSession,
                            didReceive data: Data,
                            fromPeer peerID: MCPeerID) {
        os_log("Received %d bytes from %{public}s", log: .networking, type: .debug,
               data.count, peerID.displayName)
        // Data handling would be implemented by caller
    }
    
    nonisolated func session(_ session: MCSession,
                            didReceive stream: InputStream,
                            withName streamName: String,
                            fromPeer peerID: MCPeerID) {
        os_log("Received stream %{public}s from %{public}s", log: .networking, type: .debug,
               streamName, peerID.displayName)
    }
    
    nonisolated func session(_ session: MCSession,
                            didStartReceivingResourceWithName resourceName: String,
                            fromPeer peerID: MCPeerID,
                            with progress: Progress) {
        os_log("Started receiving resource %{public}s", log: .networking, type: .debug, resourceName)
    }
    
    nonisolated func session(_ session: MCSession,
                            didFinishReceivingResourceWithName resourceName: String,
                            fromPeer peerID: MCPeerID,
                            at localURL: URL?,
                            withError error: Error?) {
        if let error = error {
            os_log("Error receiving resource: %{public}s", log: .networking, type: .error,
                   error.localizedDescription)
        } else {
            os_log("Finished receiving resource %{public}s", log: .networking, type: .debug, resourceName)
        }
    }
}

// MARK: - OSLog Extension

private extension OSLog {
    static let networking = OSLog(subsystem: "io.exo.cluster", category: "networking")
}
