resource "hcloud_ssh_key" "jonas_hahn" {
  name       = "Jonas Hahn"
  public_key = file("files/sshkey_jonas_hahn.pub")
}

resource "hcloud_ssh_key" "alois_dirnaichner" {
  name       = "Alois Dirnaichner"
  public_key = file("files/sshkey_alois_dirnaichner.pub")
}

resource "hcloud_ssh_key" "fabian_jakub" {
  name       = "Fabian Jakub"
  public_key = file("files/sshkey_fabian_jakub.pub")
}