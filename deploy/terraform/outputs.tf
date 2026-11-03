output "client_urls" {
  description = "Where each client's dashboard is reachable on this machine"
  value       = { for name, c in local.clients : name => "http://localhost:${c.host_port}" }
}
