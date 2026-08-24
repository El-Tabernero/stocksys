from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Empresa, PerfilUsuario, Categoria, Producto, GuestKey


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
