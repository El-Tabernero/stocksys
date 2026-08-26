from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Empresa, PerfilUsuario, Categoria, Producto, GuestKey, MovimientoStock


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
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        self.client.post(reverse('invitado'), {'guest_key': clave.key})

    def test_generar_clave_requiere_login(self):
        response = self.client.post(reverse('generar_clave_invitado'))
        self.assertIn(reverse('login'), response.url)

    def test_generar_clave_invitado(self):
        clave = self._generar_clave()
        self.assertIsNotNone(clave)
        self.assertTrue(clave.es_valida)
        self.assertLessEqual(clave.segundos_restantes, 600)

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
        self.assertEqual(self.client.session.get_expiry_age(), 600)

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
            key='guest-test', expires_at=timezone.now() + timedelta(minutes=10),
        )
        self.client.post(reverse('invitado'), {'guest_key': clave.key})
        self.client.post(reverse('stock_rapido', args=[self.producto.pk]), {'accion': 'vender'})
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 5)
