from datetime import timedelta
from decimal import Decimal
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Empresa, PerfilUsuario, Categoria, Producto, ProductoImagen,
    GuestKey, MovimientoStock, Cliente, Orden, OrdenItem,
)


@override_settings(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class GuestKeyTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='Demo')
        self.owner = User.objects.create_user('owner', password='pass12345')
        PerfilUsuario.objects.create(user=self.owner, empresa=self.empresa)

    def _generar_clave(self):
        self.client.login(username='owner', password='pass12345')
        self.client.post(reverse('generar_clave_invitado'))
        return GuestKey.objects.first()

    def _login_invitado(self):
        clave = GuestKey.objects.create(
            empresa=self.empresa,
            created_by=self.owner,
            key='clave-demo-123',
            expires_at=timezone.now() + timedelta(seconds=GuestKey.DURACION),
        )
        self.client.post(reverse('invitado'), {'guest_key': clave.key})

    def test_generar_clave_requiere_login(self):
        response = self.client.post(reverse('generar_clave_invitado'))
        self.assertIn(reverse('login'), response.url)

    def test_generar_clave_invitado(self):
        clave = self._generar_clave()
        self.assertIsNotNone(clave)
        self.assertTrue(clave.es_valida)
        self.assertLessEqual(clave.segundos_restantes, GuestKey.DURACION)

    def test_generar_clave_invitado_regenera(self):
        self._generar_clave()
        self._generar_clave()
        self.assertEqual(GuestKey.objects.count(), 1)

    def test_login_invitado_con_clave_valida(self):
        clave = self._generar_clave()
        self.client.logout()
        response = self.client.post(reverse('invitado'), {'guest_key': clave.key})
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(self.client.session.get('is_guest'))
        self.assertEqual(self.client.session.get_expiry_age(), GuestKey.DURACION)

    def test_login_invitado_con_clave_invalida(self):
        response = self.client.post(reverse('invitado'), {'guest_key': 'clave-inexistente'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get('is_guest'))

    def test_invitado_puede_crear_categoria(self):
        self._login_invitado()
        response = self.client.post(reverse('categoria_agregar'), {'nombre': 'Teclados'})
        self.assertRedirects(response, reverse('categoria_lista'))
        self.assertTrue(Categoria.objects.filter(empresa=self.empresa, nombre='Teclados').exists())

    def test_invitado_no_puede_eliminar_categoria(self):
        categoria = Categoria.objects.create(empresa=self.empresa, nombre='Guitarras')
        self._login_invitado()
        response = self.client.post(reverse('categoria_eliminar', args=[categoria.pk]))
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(Categoria.objects.filter(pk=categoria.pk).exists())

    def test_invitado_no_puede_crear_producto(self):
        self._login_invitado()
        response = self.client.post(reverse('producto_agregar'), {'nombre': 'Cable', 'stock_actual': 1})
        self.assertRedirects(response, reverse('dashboard'))
        self.assertFalse(Producto.objects.filter(nombre='Cable').exists())

    def test_dueño_puede_eliminar_categoria(self):
        categoria = Categoria.objects.create(empresa=self.empresa, nombre='Guitarras')
        self.client.login(username='owner', password='pass12345')
        response = self.client.post(reverse('categoria_eliminar', args=[categoria.pk]))
        self.assertRedirects(response, reverse('categoria_lista'))
        self.assertFalse(Categoria.objects.filter(pk=categoria.pk).exists())


@override_settings(
    DEBUG=True, SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
)
class StockDirectionTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='T')
        self.owner = User.objects.create_user('o', password='p12345')
        PerfilUsuario.objects.create(user=self.owner, empresa=self.empresa)
        self.producto = Producto.objects.create(
            empresa=self.empresa, nombre='Clavos', stock_actual=10,
        )

    def test_entrada_increase_stock(self):
        MovimientoStock.objects.create(
            empresa=self.empresa, producto=self.producto,
            usuario=self.owner, tipo='IN', cantidad=5,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 15)

    def test_salida_decrease_stock(self):
        MovimientoStock.objects.create(
            empresa=self.empresa, producto=self.producto,
            usuario=self.owner, tipo='OUT', cantidad=4,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 6)

    def test_ajuste_absolute_value(self):
        MovimientoStock.objects.create(
            empresa=self.empresa, producto=self.producto,
            usuario=self.owner, tipo='ADJ', cantidad=3,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 13)


@override_settings(
    DEBUG=True, SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
)
class PrecioParseTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='P')
        self.owner = User.objects.create_user('u', password='p12345')
        PerfilUsuario.objects.create(user=self.owner, empresa=self.empresa)
        self.client.login(username='u', password='p12345')

    def _post_precio(self, value):
        return self.client.post(reverse('producto_agregar'), {
            'nombre': 'Tornillo', 'precio_venta': value, 'precio_costo': value,
            'stock_actual': 1, 'stock_minimo': 1,
        })

    def test_plain_integer(self):
        self._post_precio('1200')
        p = Producto.objects.get(nombre='Tornillo')
        self.assertEqual(p.precio_venta, 1200)

    def test_thousands_dots(self):
        self._post_precio('1.200.000')
        p = Producto.objects.get(nombre='Tornillo')
        self.assertEqual(p.precio_venta, 1200000)

    def test_comma_decimal(self):
        self._post_precio('1500,50')
        p = Producto.objects.get(nombre='Tornillo')
        self.assertEqual(p.precio_venta, 1500.5)

    def test_dots_and_commas(self):
        self._post_precio('1.250.000,99')
        p = Producto.objects.get(nombre='Tornillo')
        self.assertEqual(p.precio_venta, Decimal('1250000.99'))

    def test_three_digit_dot_is_thousands(self):
        self._post_precio('1.200')
        p = Producto.objects.get(nombre='Tornillo')
        self.assertEqual(p.precio_venta, 1200)


@override_settings(
    DEBUG=True, SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
)
class StockRapidoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='R')
        self.owner = User.objects.create_user('seller', password='p12345')
        PerfilUsuario.objects.create(user=self.owner, empresa=self.empresa)
        self.producto = Producto.objects.create(
            empresa=self.empresa, nombre='Tuerca', stock_actual=5,
        )
        self.client.login(username='seller', password='p12345')

    def test_vender_decreases_stock(self):
        self.client.post(reverse('stock_rapido', args=[self.producto.pk]), {'accion': 'vender'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 4)
        self.assertEqual(
            MovimientoStock.objects.get(producto=self.producto).tipo,
            MovimientoStock.TipoMovimiento.SALIDA,
        )

    def test_reponer_increase_stock(self):
        self.client.post(reverse('stock_rapido', args=[self.producto.pk]), {'accion': 'reponer'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 6)
        self.assertEqual(
            MovimientoStock.objects.get(producto=self.producto).tipo,
            MovimientoStock.TipoMovimiento.ENTRADA,
        )

    def test_vender_sin_stock_blocked(self):
        self.producto.stock_actual = 0
        self.producto.save()
        self.client.post(reverse('stock_rapido', args=[self.producto.pk]), {'accion': 'vender'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 0)
        self.assertFalse(MovimientoStock.objects.filter(producto=self.producto).exists())

    def test_invitado_blocked(self):
        self.client.logout()
        clave = GuestKey.objects.create(
            empresa=self.empresa, created_by=self.owner,
            key='guest-test', expires_at=timezone.now() + timedelta(seconds=GuestKey.DURACION),
        )
        self.client.post(reverse('invitado'), {'guest_key': clave.key})
        self.client.post(reverse('stock_rapido', args=[self.producto.pk]), {'accion': 'vender'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 5)


@override_settings(
    DEBUG=True, SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
)
class ReporteTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='R')
        self.owner = User.objects.create_user('rep', password='p12345')
        PerfilUsuario.objects.create(user=self.owner, empresa=self.empresa)
        self.client.login(username='rep', password='p12345')

        self.a = Producto.objects.create(empresa=self.empresa, nombre='A', stock_actual=0, stock_minimo=3, precio_venta=10, precio_costo=6)
        self.b = Producto.objects.create(empresa=self.empresa, nombre='B', stock_actual=1, stock_minimo=5, precio_venta=20, precio_costo=10)
        self.c = Producto.objects.create(empresa=self.empresa, nombre='C', stock_actual=50, stock_minimo=5, precio_venta=100, precio_costo=40)

        # La creación de movimientos muta stock; los movimientos registran la actividad del período.
        MovimientoStock.objects.create(empresa=self.empresa, producto=self.a, usuario=self.owner, tipo='OUT', cantidad=2)
        MovimientoStock.objects.create(empresa=self.empresa, producto=self.b, usuario=self.owner, tipo='OUT', cantidad=3)
        MovimientoStock.objects.create(empresa=self.empresa, producto=self.b, usuario=self.owner, tipo='IN', cantidad=1)

        # El reporte usa el stock_actual persistido para los listados de stock.
        Producto.objects.filter(pk=self.a.pk).update(stock_actual=0)
        Producto.objects.filter(pk=self.b.pk).update(stock_actual=1)
        Producto.objects.filter(pk=self.c.pk).update(stock_actual=50)

    def test_report_requiere_login(self):
        self.client.logout()
        r = self.client.get(reverse('reporte'))
        self.assertIn(reverse('login'), r.url)

    def test_report_invitado_bloqueado(self):
        self.client.logout()
        clave = GuestKey.objects.create(empresa=self.empresa, created_by=self.owner, key='g',
                                        expires_at=timezone.now() + timedelta(seconds=GuestKey.DURACION))
        self.client.post(reverse('invitado'), {'guest_key': clave.key})
        r = self.client.get(reverse('reporte'))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, reverse('dashboard'))

    def test_metricas(self):
        r = self.client.get(reverse('reporte'), {'rango': '30d'})
        self.assertEqual(r.context['unidades_vendidas'], 5)
        self.assertEqual(r.context['unidades_compradas'], 1)
        self.assertEqual(r.context['plata_vendida'], Decimal('80'))
        self.assertEqual(r.context['plata_comprada'], Decimal('10'))

    def test_sin_stock(self):
        r = self.client.get(reverse('reporte'), {'rango': '30d'})
        items = r.context['productos_sin_stock']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['producto'].nombre, 'A')
        self.assertEqual(items[0]['vendido'], 2)

    def test_stock_bajo(self):
        r = self.client.get(reverse('reporte'), {'rango': '30d'})
        nombres = [p.nombre for p in r.context['productos_stock_bajo']]
        self.assertIn('B', nombres)
        self.assertNotIn('C', nombres)

    def test_top_vendidos(self):
        r = self.client.get(reverse('reporte'), {'rango': '30d'})
        top = r.context['productos_top']
        self.assertEqual([p.nombre for p in top], ['B', 'A'])

    def test_sin_rotacion(self):
        r = self.client.get(reverse('reporte'), {'rango': '30d'})
        nombres = [p.nombre for p in r.context['productos_sin_rotacion']]
        self.assertIn('C', nombres)
        self.assertNotIn('A', nombres)
        self.assertNotIn('B', nombres)

    def test_rango_libre_filtra(self):
        ayer = timezone.now() - timedelta(days=2)
        MovimientoStock.objects.filter(producto=self.c).update(fecha=ayer)
        # mover todas las ventas de hoy a un movimiento viejo filtrado fuera
        MovimientoStock.objects.filter(producto__in=[self.a, self.b]).update(fecha=ayer)
        r = self.client.get(reverse('reporte'), {'rango': 'libre', 'desde': '', 'hasta': ''})
        # si no hay ventas en el rango libre (hoy), la C vendida ayer no cuenta
        nombres = [p.nombre for p in r.context['productos_sin_rotacion']]
        self.assertIn('C', nombres)

    def test_csv_export(self):
        r = self.client.get(reverse('reporte'), {'rango': '30d', 'export': 'csv'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/csv', r['Content-Type'])
        contenido = b''.join(r.streaming_content).decode('utf-8-sig')
        self.assertIn('Producto', contenido)
        self.assertIn('SIN STOCK', contenido)
        self.assertIn('MÁS VENDIDO', contenido)

    def test_pdf_export(self):
        r = self.client.get(reverse('reporte'), {'rango': '30d', 'export': 'pdf'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')


@override_settings(
    DEBUG=True, SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
)
class ProductoDetalleTests(TestCase):
    def setUp(self):
        import io
        import shutil
        import tempfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        self._SimpleUploadedFile = SimpleUploadedFile
        buf = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(buf, format='PNG')
        self._png = buf.getvalue()

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        self._media_override = override_settings(MEDIA_ROOT=media)
        self._media_override.enable()
        self.addCleanup(self._media_override.disable)

        self.empresa = Empresa.objects.create(nombre='Det')
        self.empresa2 = Empresa.objects.create(nombre='Otra')
        self.owner = User.objects.create_user('detuser', password='p12345')
        PerfilUsuario.objects.create(user=self.owner, empresa=self.empresa)
        self.producto = Producto.objects.create(
            empresa=self.empresa, nombre='Cafetera',
            descripcion='Cafetera italiana de aluminio, 6 tazas.',
            precio_venta=Decimal('25000.00'), stock_actual=3,
        )
        self.ajeno = Producto.objects.create(
            empresa=self.empresa2, nombre='Ajeno',
            descripcion='Producto de otra empresa',
        )

    def _login_invitado(self):
        self.client.logout()
        clave = GuestKey.objects.create(
            empresa=self.empresa, created_by=self.owner,
            key='guest-det', expires_at=timezone.now() + timedelta(seconds=GuestKey.DURACION),
        )
        self.client.post(reverse('invitado'), {'guest_key': clave.key})

    def test_detalle_muestra_descripcion(self):
        self.client.login(username='detuser', password='p12345')
        r = self.client.get(reverse('producto_detalle', args=[self.producto.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Cafetera italiana de aluminio')
        self.assertContains(r, 'Cafetera')

    def test_detalle_404_empresa_ajena(self):
        self.client.login(username='detuser', password='p12345')
        r = self.client.get(reverse('producto_detalle', args=[self.ajeno.pk]))
        self.assertEqual(r.status_code, 404)

    def test_detalle_requiere_login(self):
        r = self.client.get(reverse('producto_detalle', args=[self.producto.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('login'), r['Location'])

    def test_invitado_ve_detalle_sin_botones(self):
        self._login_invitado()
        r = self.client.get(reverse('producto_detalle', args=[self.producto.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Cafetera italiana de aluminio')
        self.assertNotContains(r, reverse('producto_editar', args=[self.producto.pk]))

    def test_lista_linkea_al_detalle(self):
        self.client.login(username='detuser', password='p12345')
        r = self.client.get(reverse('producto_lista'))
        self.assertContains(r, reverse('producto_detalle', args=[self.producto.pk]))

    def test_subir_imagen_a_galeria(self):
        self.client.login(username='detuser', password='p12345')
        img = self._SimpleUploadedFile('foto.png', self._png, content_type='image/png')
        r = self.client.post(
            reverse('producto_imagen_subir', args=[self.producto.pk]),
            {'imagen': img},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.producto.imagenes.count(), 1)
        r = self.client.get(reverse('producto_detalle', args=[self.producto.pk]))
        self.assertContains(r, '/media/productos/')

    def test_invitado_no_puede_subir_imagen(self):
        self._login_invitado()
        img = self._SimpleUploadedFile('foto.png', self._png, content_type='image/png')
        self.client.post(
            reverse('producto_imagen_subir', args=[self.producto.pk]),
            {'imagen': img},
        )
        self.assertEqual(self.producto.imagenes.count(), 0)

    def test_eliminar_imagen(self):
        self.client.login(username='detuser', password='p12345')
        img = self._SimpleUploadedFile('foto.png', self._png, content_type='image/png')
        self.client.post(
            reverse('producto_imagen_subir', args=[self.producto.pk]),
            {'imagen': img},
        )
        imagen = self.producto.imagenes.first()
        self.client.post(
            reverse('producto_imagen_eliminar', args=[self.producto.pk, imagen.pk]),
        )
        self.assertEqual(self.producto.imagenes.count(), 0)

    def test_agregar_imagen_por_link(self):
        self.client.login(username='detuser', password='p12345')
        r = self.client.post(
            reverse('producto_imagen_agregar', args=[self.producto.pk]),
            {'url': 'https://i.imgur.com/abc123.png'},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.producto.imagenes.count(), 1)
        r = self.client.get(reverse('producto_detalle', args=[self.producto.pk]))
        self.assertContains(r, 'https://i.imgur.com/abc123.png')
        self.assertContains(r, 'onerror=')
        self.assertContains(r, 'i.imgur.com')

    def test_link_esquema_invalido_rechazado(self):
        self.client.login(username='detuser', password='p12345')
        self.client.post(
            reverse('producto_imagen_agregar', args=[self.producto.pk]),
            {'url': 'ftp://servidor/foto.png'},
        )
        self.client.post(
            reverse('producto_imagen_agregar', args=[self.producto.pk]),
            {'url': 'esto-no-es-una-url'},
        )
        self.assertEqual(self.producto.imagenes.count(), 0)

    def test_invitado_no_puede_agregar_link(self):
        self._login_invitado()
        self.client.post(
            reverse('producto_imagen_agregar', args=[self.producto.pk]),
            {'url': 'https://i.imgur.com/abc.png'},
        )
        self.assertEqual(self.producto.imagenes.count(), 0)

    def test_src_y_origen_dual(self):
        link = ProductoImagen.objects.create(
            producto=self.producto, url='https://ejemplo.com/f.jpg',
        )
        self.assertEqual(link.src, 'https://ejemplo.com/f.jpg')
        self.assertEqual(link.origen, 'ejemplo.com')

        self.client.login(username='detuser', password='p12345')
        img = self._SimpleUploadedFile('foto.png', self._png, content_type='image/png')
        self.client.post(
            reverse('producto_imagen_subir', args=[self.producto.pk]),
            {'imagen': img},
        )
        archivo = self.producto.imagenes.exclude(pk=link.pk).first()
        self.assertTrue(archivo.src.startswith('/media/productos/'))
        self.assertEqual(archivo.origen, 'Archivo local')

    def test_formularios_solo_owner(self):
        self.client.login(username='detuser', password='p12345')
        r = self.client.get(reverse('producto_detalle', args=[self.producto.pk]))
        self.assertContains(r, reverse('producto_imagen_agregar', args=[self.producto.pk]))
        self.assertContains(r, reverse('producto_imagen_subir', args=[self.producto.pk]))
        self._login_invitado()
        r = self.client.get(reverse('producto_detalle', args=[self.producto.pk]))
        self.assertNotContains(r, reverse('producto_imagen_agregar', args=[self.producto.pk]))
        self.assertNotContains(r, reverse('producto_imagen_subir', args=[self.producto.pk]))


@override_settings(
    DEBUG=True, SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
)
class ApiPublicaTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='Tienda A', activa=True)
        self.empresa_b = Empresa.objects.create(nombre='Tienda B', activa=True)
        self.cat = Categoria.objects.create(empresa=self.empresa, nombre='Electronica')
        self.p1 = Producto.objects.create(
            empresa=self.empresa, categoria=self.cat, nombre='Auriculares',
            descripcion='Bluetooth con cancelacion de ruido',
            precio_venta=Decimal('15000.00'), stock_actual=3,
        )
        self.p2 = Producto.objects.create(
            empresa=self.empresa, nombre='Parlante',
            precio_venta=Decimal('9000.00'), stock_actual=0,
        )
        self.ajeno = Producto.objects.create(
            empresa=self.empresa_b, nombre='Producto ajeno',
            precio_venta=Decimal('1000.00'), stock_actual=5,
        )
        self.url_lista = reverse('api_productos', args=[self.empresa.pk])

    def _get(self, url, params=None):
        return self.client.get(url, params or {}, HTTP_ACCEPT='application/json')

    def _post(self, url, payload):
        return self.client.post(url, payload, content_type='application/json')

    def test_catalogo_aislado_por_empresa(self):
        r = self._get(self.url_lista)
        self.assertEqual(r.status_code, 200)
        nombres = [p['nombre'] for p in r.json()]
        self.assertIn('Auriculares', nombres)
        self.assertNotIn('Producto ajeno', nombres)

    def test_catalogo_filtros_q_y_stock(self):
        r = self._get(self.url_lista, {'q': 'auri'})
        self.assertEqual(len(r.json()), 1)
        r = self._get(self.url_lista, {'solo_con_stock': '1'})
        nombres = [p['nombre'] for p in r.json()]
        self.assertIn('Auriculares', nombres)
        self.assertNotIn('Parlante', nombres)

    def test_detalle_publico_completo(self):
        ProductoImagen.objects.create(producto=self.p1, url='https://i.imgur.com/x.png')
        r = self._get(reverse('api_producto_detalle', args=[self.empresa.pk, self.p1.pk]))
        data = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(data['descripcion'], 'Bluetooth con cancelacion de ruido')
        self.assertEqual(data['categoria'], 'Electronica')
        self.assertEqual(data['precio_venta'], '15000.00')
        self.assertEqual(data['imagenes'][0]['src'], 'https://i.imgur.com/x.png')
        self.assertEqual(data['imagenes'][0]['origen'], 'i.imgur.com')
        self.assertTrue(data['disponible'])

    def test_detalle_disponible_false_sin_stock(self):
        r = self._get(reverse('api_producto_detalle', args=[self.empresa.pk, self.p2.pk]))
        self.assertFalse(r.json()['disponible'])

    def test_detalle_404_producto_ajeno(self):
        r = self._get(reverse('api_producto_detalle', args=[self.empresa.pk, self.ajeno.pk]))
        self.assertEqual(r.status_code, 404)

    def test_empresa_inactiva_404(self):
        self.empresa.activa = False
        self.empresa.save()
        r = self._get(self.url_lista)
        self.assertEqual(r.status_code, 404)

    def test_categorias_endpoint(self):
        r = self._get(reverse('api_categorias', args=[self.empresa.pk]))
        nombres = [c['nombre'] for c in r.json()]
        self.assertIn('Electronica', nombres)

    def test_checkout_crea_orden_total_server(self):
        payload = {
            'nombre': 'Maria Lopez', 'email': 'maria@correo.com',
            'items': [{'producto': self.p1.pk, 'cantidad': 2}],
        }
        r = self._post(reverse('api_crear_orden', args=[self.empresa.pk]), payload)
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(Decimal(data['total']), Decimal('30000.00'))
        self.assertEqual(data['estado'], 'PENDIENTE')
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(Orden.objects.count(), 1)
        self.assertTrue(Cliente.objects.filter(
            empresa=self.empresa, email='maria@correo.com',
        ).exists())

    def test_checkout_descuenta_stock(self):
        payload = {
            'nombre': 'Ana', 'email': 'ana@correo.com',
            'items': [{'producto': self.p1.pk, 'cantidad': 2}],
        }
        r = self._post(reverse('api_crear_orden', args=[self.empresa.pk]), payload)
        self.assertEqual(r.status_code, 201)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock_actual, 1)
        mov = MovimientoStock.objects.get(producto=self.p1)
        self.assertEqual(mov.tipo, MovimientoStock.TipoMovimiento.SALIDA)
        self.assertEqual(mov.cantidad, 2)
        self.assertTrue(mov.motivo.startswith('Orden'))

    def test_checkout_sin_stock_400(self):
        payload = {
            'nombre': 'Ana', 'email': 'ana@correo.com',
            'items': [{'producto': self.p1.pk, 'cantidad': 50}],
        }
        r = self._post(reverse('api_crear_orden', args=[self.empresa.pk]), payload)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Orden.objects.count(), 0)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock_actual, 3)

    def test_checkout_items_vacios_400(self):
        payload = {'nombre': 'Ana', 'email': 'ana@correo.com', 'items': []}
        r = self._post(reverse('api_crear_orden', args=[self.empresa.pk]), payload)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Orden.objects.count(), 0)

    def test_checkout_producto_ajeno_400(self):
        payload = {
            'nombre': 'Ana', 'email': 'ana@correo.com',
            'items': [{'producto': self.ajeno.pk, 'cantidad': 1}],
        }
        r = self._post(reverse('api_crear_orden', args=[self.empresa.pk]), payload)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Orden.objects.count(), 0)

    def test_checkout_email_invalido_400(self):
        payload = {
            'nombre': 'Ana', 'email': 'no-es-email',
            'items': [{'producto': self.p1.pk, 'cantidad': 1}],
        }
        r = self._post(reverse('api_crear_orden', args=[self.empresa.pk]), payload)
        self.assertEqual(r.status_code, 400)

    def test_orden_detalle_por_uuid(self):
        payload = {
            'nombre': 'Ana', 'email': 'ana@correo.com',
            'items': [{'producto': self.p1.pk, 'cantidad': 1}],
        }
        r = self._post(reverse('api_crear_orden', args=[self.empresa.pk]), payload)
        orden_id = r.json()['id']
        r = self._get(reverse('api_orden_detalle', args=[orden_id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Decimal(r.json()['total']), Decimal('15000.00'))
        r = self._get(reverse('api_orden_detalle', args=[str(uuid.uuid4())]))
        self.assertEqual(r.status_code, 404)


@override_settings(
    DEBUG=True, SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
)
class MovimientoStockReglasTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='E1')
        self.empresa2 = Empresa.objects.create(nombre='E2')
        self.owner = User.objects.create_user('reglas', password='p12345')
        PerfilUsuario.objects.create(user=self.owner, empresa=self.empresa)
        self.producto = Producto.objects.create(
            empresa=self.empresa, nombre='Item', stock_actual=5,
        )

    def _crear(self, **kwargs):
        base = dict(
            empresa=self.empresa, producto=self.producto,
            usuario=self.owner, tipo='OUT', cantidad=2, motivo='x',
        )
        base.update(kwargs)
        return MovimientoStock.objects.create(**base)

    def test_cantidad_cero_invalida(self):
        with self.assertRaises(ValidationError):
            self._crear(cantidad=0)

    def test_cantidad_negativa_invalida(self):
        with self.assertRaises(ValidationError):
            self._crear(cantidad=-3)

    def test_empresa_incoherente_invalida(self):
        with self.assertRaises(ValidationError):
            self._crear(empresa=self.empresa2)

    def test_stock_se_acumula(self):
        self._crear(cantidad=2)
        self._crear(cantidad=1)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 2)
        self.assertEqual(MovimientoStock.objects.count(), 2)

    def test_entrada_aumenta_stock(self):
        self._crear(tipo='IN', cantidad=4)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 9)
