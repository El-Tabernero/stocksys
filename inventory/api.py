from decimal import Decimal

from django.db import connection, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Categoria, Cliente, Empresa, MovimientoStock, Orden, OrdenItem, Producto
from .serializers import (
    CategoriaSerializer, CheckoutSerializer, OrdenSalidaSerializer,
    ProductoPublicoSerializer,
)


def _empresa_activa(empresa_pk):
    return get_object_or_404(Empresa, pk=empresa_pk, activa=True)


def _productos_qs():
    return (
        Producto.objects
        .select_related('categoria')
        .prefetch_related('imagenes', 'opciones__atributo')
    )


@api_view(['GET'])
def api_productos(request, empresa_pk):
    empresa = _empresa_activa(empresa_pk)
    productos = _productos_qs().filter(empresa=empresa)

    q = request.GET.get('q', '').strip()
    if q:
        productos = productos.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))

    categoria = request.GET.get('categoria')
    if categoria:
        productos = productos.filter(categoria_id=categoria)

    if request.GET.get('solo_con_stock') in ('1', 'true'):
        productos = productos.filter(stock_actual__gt=0)

    return Response(ProductoPublicoSerializer(productos, many=True).data)


@api_view(['GET'])
def api_producto_detalle(request, empresa_pk, pk):
    empresa = _empresa_activa(empresa_pk)
    producto = get_object_or_404(_productos_qs(), pk=pk, empresa=empresa)
    return Response(ProductoPublicoSerializer(producto).data)


@api_view(['GET'])
def api_categorias(request, empresa_pk):
    empresa = _empresa_activa(empresa_pk)
    categorias = Categoria.objects.filter(empresa=empresa)
    return Response(CategoriaSerializer(categorias, many=True).data)


@api_view(['POST'])
def api_crear_orden(request, empresa_pk):
    empresa = _empresa_activa(empresa_pk)
    form = CheckoutSerializer(data=request.data)
    if not form.is_valid():
        return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

    datos = form.validated_data

    cantidades = {}
    for item in datos['items']:
        pid = item['producto']
        cantidades[pid] = cantidades.get(pid, 0) + item['cantidad']

    with transaction.atomic():
        qs = Producto.objects.filter(pk__in=cantidades.keys(), empresa=empresa)
        if connection.features.has_select_for_update:
            qs = qs.select_for_update()
        productos = {p.pk: p for p in qs}

        faltantes = [pid for pid in cantidades if pid not in productos]
        if faltantes:
            return Response(
                {'items': [f'Productos no encontrados en esta tienda: {faltantes}']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sin_stock = [
            p.nombre for p in productos.values()
            if p.stock_actual < cantidades[p.pk]
        ]
        if sin_stock:
            return Response(
                {'items': [f'Sin stock suficiente: {", ".join(sin_stock)}']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cliente, _ = Cliente.objects.get_or_create(
            empresa=empresa,
            email=datos['email'],
            defaults={
                'nombre': datos['nombre'],
                'telefono': datos.get('telefono', ''),
            },
        )

        total = sum(
            (productos[pid].precio_venta * cant for pid, cant in cantidades.items()),
            Decimal('0'),
        )

        orden = Orden.objects.create(
            empresa=empresa,
            cliente=cliente,
            total=total,
            direccion_envio=datos.get('direccion_envio', ''),
        )

        for pid, cant in cantidades.items():
            producto = productos[pid]
            OrdenItem.objects.create(
                orden=orden,
                producto=producto,
                cantidad=cant,
                precio_unitario=producto.precio_venta,
            )
            MovimientoStock.objects.create(
                empresa=empresa,
                producto=producto,
                usuario=None,
                tipo=MovimientoStock.TipoMovimiento.SALIDA,
                cantidad=cant,
                motivo=f'Orden {orden.id}',
            )

    return Response(OrdenSalidaSerializer(orden).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def api_orden_detalle(request, pk):
    orden = get_object_or_404(
        Orden.objects.prefetch_related('items__producto'), pk=pk,
    )
    return Response(OrdenSalidaSerializer(orden).data)
