from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class Empresa(models.Model):
    nombre = models.CharField(max_length=150)
    cuit_o_id = models.CharField(max_length=20, blank=True, null=True)
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class PerfilUsuario(models.Model):
    class Rol(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        EMPLEADO = 'EMPLEADO', 'Empleado'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='usuarios')
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.EMPLEADO)

    def __str__(self):
        return f"{self.user.username} - {self.empresa.nombre}"


class Categoria(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='categorias')
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('empresa', 'nombre')
        verbose_name_plural = "Categorías"

    def __str__(self):
        return f"{self.nombre} ({self.empresa.nombre})"


class Producto(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='productos')
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='productos', blank=True, null=True)

    codigo_barras = models.CharField(max_length=50, blank=True, null=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)

    precio_costo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_venta = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    stock_actual = models.IntegerField(default=0)
    stock_minimo = models.IntegerField(default=5)

    class Meta:
        unique_together = ('empresa', 'codigo_barras')

    def __str__(self):
        return f"{self.nombre} - Stock: {self.stock_actual}"

    def clean(self):
        if self.categoria and self.categoria.empresa_id != self.empresa_id:
            raise ValidationError("La categoría seleccionada no pertenece a esta empresa.")


class MovimientoStock(models.Model):
    class TipoMovimiento(models.TextChoices):
        ENTRADA = 'IN', 'Entrada / Compra'
        SALIDA = 'OUT', 'Salida / Venta'
        AJUSTE = 'ADJ', 'Ajuste de Inventario'

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='movimientos')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='movimientos')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    tipo = models.CharField(max_length=3, choices=TipoMovimiento.choices)
    cantidad = models.IntegerField()
    motivo = models.CharField(max_length=255, blank=True, null=True)
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.producto.nombre} ({self.cantidad})"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.producto.stock_actual += self.cantidad
            self.producto.save()
        super().save(*args, **kwargs)
