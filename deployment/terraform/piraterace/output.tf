output "piraterace_dev" {
  value = hcloud_server.piraterace_dev.ipv4_address
}

resource "local_file" "ansible_inventory" {
    content     = <<EOT
piraterace_dev ansible_user=root ansible_host=${hcloud_server.piraterace_dev.ipv4_address}
EOT
    filename = "${path.module}/../../ansible/hosts"
}