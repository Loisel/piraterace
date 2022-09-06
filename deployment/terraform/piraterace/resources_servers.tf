locals {
  datacenter = "nbg1-dc3"
}

resource "hcloud_primary_ip" "piraterace_dev" {
  name = "piraterace_dev"
  type = "ipv4"
  datacenter = local.datacenter
  assignee_type = "server"
  auto_delete = false
  delete_protection = true
  lifecycle {
    prevent_destroy = true
  }
}

resource "hcloud_server" "piraterace_dev" {
  name = "piraterace-dev"
  server_type = "cpx11"
  image = "ubuntu-22.04"
  location = "nbg1"
  ssh_keys = [
    hcloud_ssh_key.jonas_hahn.id,
    hcloud_ssh_key.alois_dirnaichner.id,
    hcloud_ssh_key.fabian_jakub.id,
  ]
  public_net {
    ipv4 = hcloud_primary_ip.piraterace_dev.id
  }
  delete_protection = true
  rebuild_protection = true
  lifecycle {
    prevent_destroy = true
  }
}
