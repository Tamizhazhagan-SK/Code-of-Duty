resource "aws_db_instance" "payments" {
  engine          = "postgres"
  username        = "payments"
  master_password = "{{gen:password}}"
}
