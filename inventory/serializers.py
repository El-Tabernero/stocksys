from rest_framework import serializers

from .models import Categoria, Orden, OrdenItem, Producto


class ProductoImagenSerializer(serializers.Serializer):
    src = serializers.CharField(allow_null=True)
    origen = serializers.CharField()


class ProductoPublicoSerializer(serializers.ModelSerializer):
    categoria = serializers.CharField(source='categoria.nombre', default=None)
    imagenes = ProductoImagenSerializer(many=True, read_only=True)
    atributos = serializers.SerializerMethodField()
    disponible = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            'id', 'nombre', 'descripcion', 'categoria', 'precio_venta',
            'atributos', 'imagenes', 'disponible',
        ]

    def get_atributos(self, obj):
        return obj.atributos_agrupados

    def get_disponible(self, obj):
        return obj.stock_actual > 0


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ['id', 'nombre', 'descripcion']


class OrdenItemInputSerializer(serializers.Serializer):
    producto = serializers.IntegerField(min_value=1)
    cantidad = serializers.IntegerField(min_value=1, max_value=1000)


class CheckoutSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True, default='')
    direccion_envio = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    items = serializers.ListField(child=OrdenItemInputSerializer(), allow_empty=False)


class OrdenItemSalidaSerializer(serializers.ModelSerializer):
    producto = serializers.CharField(source='producto.nombre')
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrdenItem
        fields = ['producto', 'cantidad', 'precio_unitario', 'subtotal']


class OrdenSalidaSerializer(serializers.ModelSerializer):
    items = OrdenItemSalidaSerializer(many=True, read_only=True)

    class Meta:
        model = Orden
        fields = ['id', 'estado', 'total', 'direccion_envio', 'created_at', 'items']
