# A local Kubernetes cluster (Kind) and three Helm releases of Argus, one per simulated client.
# Local only: nothing here touches a cloud account.

locals {
  clients = {
    acme    = { node_port = 30081, host_port = 8081 }
    globex  = { node_port = 30082, host_port = 8082 }
    initech = { node_port = 30083, host_port = 8083 }
  }
  chart = "${path.module}/../helm/argus"
}

resource "kind_cluster" "argus" {
  name           = var.cluster_name
  wait_for_ready = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"
      # publish each client's web NodePort on the laptop
      dynamic "extra_port_mappings" {
        for_each = local.clients
        content {
          container_port = extra_port_mappings.value.node_port
          host_port      = extra_port_mappings.value.host_port
        }
      }
    }
  }
}

# Build the images locally and load them into the cluster (a Kind cluster cannot pull them from the laptop's Docker).
resource "terraform_data" "images" {
  depends_on = [kind_cluster.argus]
  triggers_replace = [
    sha1(join("", [for f in fileset("${path.module}/../../api", "*.py") : filesha1("${path.module}/../../api/${f}")])),
    sha1(join("", [for f in fileset("${path.module}/../../web/app", "**/*.tsx") : filesha1("${path.module}/../../web/app/${f}")])),
  ]
  provisioner "local-exec" {
    working_dir = "${path.module}/../.."
    command     = <<-EOT
      docker build -t argus-api:dev -f Dockerfile.api . &&
      docker build -t argus-web:dev web &&
      kind load docker-image argus-api:dev argus-web:dev --name ${var.cluster_name}
    EOT
  }
}

provider "helm" {
  kubernetes {
    config_path = kind_cluster.argus.kubeconfig_path
  }
}

resource "helm_release" "client" {
  for_each   = local.clients
  depends_on = [terraform_data.images]

  name             = "argus-${each.key}"
  namespace        = each.key
  create_namespace = true
  chart            = local.chart
  values           = [file("${path.module}/../helm/values-${each.key}.yaml")]
  wait             = true
  timeout          = 600
}
