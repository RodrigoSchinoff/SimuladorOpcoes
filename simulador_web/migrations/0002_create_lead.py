from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("simulador_web", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Lead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120)),
                ("email", models.EmailField(max_length=254)),
                ("whatsapp", models.CharField(max_length=20)),
                ("cpf", models.CharField(max_length=14)),
                ("plano_interesse", models.CharField(choices=[("trial", "Trial"), ("pro", "Pro")], max_length=10)),
                ("observacao", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("novo", "Novo"), ("contatado", "Contatado"), ("convertido", "Convertido")], default="novo", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
