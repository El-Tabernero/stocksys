import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import F, Q, Count
from django.utils import timezone
from .models import (
    Empresa, PerfilUsuario, Categoria, Atributo, OpcionAtributo,
    Producto, MovimientoStock, GuestKey,
)
from .decorators import bloquear_invitados


def parse_precio(raw):
    """Convierte formatos argentinos ($ 1.250.000,50) a Decimal-compatible."""
    s = str(raw or '').strip().replace('$', '').replace(' ', '')
    if not s:
        return None
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    elif s.count('.') > 1:
        s = s.replace('.', '')
    else:
        partes = s.split('.')
        if len(partes) == 2 and len(partes[1]) == 3:
            s = s.replace('.', '')
    return s


def _precio_o_error(request, raw, etiqueta):
    valor_limpio = parse_precio(raw)
    try:
        return Decimal(valor_limpio) if valor_limpio else Decimal('0')
    except InvalidOperation:
        messages.error(request, f'Precio {etiqueta} inválido. Ejemplos válidos: 1500, 1.250.000 o 1250,50.')
        return None


def index(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'inventory/index.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario o contraseña inválidos.')
    return render(request, 'inventory/login.html')


def logout_view(request):
    logout(request)
    return redirect('index')


def _obtener_usuario_invitado(empresa):
    username = f'invitado_{empresa.pk}'
    user = User.objects.filter(username=username).first()
    if user is None:
        user = User.objects.create_user(username=username, password=None)
        PerfilUsuario.objects.create(user=user, empresa=empresa, rol=PerfilUsuario.Rol.EMPLEADO)
    return user


def _iniciar_sesion_invitado(request, clave):
    user = _obtener_usuario_invitado(clave.empresa)
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)
    request.session['is_guest'] = True
    request.session['guest_expires_at'] = (timezone.now() + timedelta(minutes=10)).isoformat()
    request.session['guest_intentos'] = 0
    request.session.set_expiry(600)
    messages.success(request, f'Sesión de invitado iniciada en "{clave.empresa.nombre}". Tenés 10 minutos de acceso.')
    return redirect('dashboard')


def invitado(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        raw_key = request.POST.get('guest_key', '').strip()
        intentos = request.session.get('guest_intentos', 0)

        if intentos >= 5:
            messages.error(request, 'Demasiados intentos fallidos. Esperá 10 minutos e intentá de nuevo.')
            return redirect('index')

        if not raw_key:
            messages.error(request, 'Ingresá la clave de invitado.')
        else:
            clave = GuestKey.objects.select_related('empresa').filter(key=raw_key).first()
            if clave and clave.es_valida:
                return _iniciar_sesion_invitado(request, clave)
            intentos += 1
            request.session['guest_intentos'] = intentos
            request.session.set_expiry(600)
            messages.error(request, 'Clave de invitado inválida o vencida.')

    return render(request, 'inventory/invitado.html')


@login_required(login_url='login')
@bloquear_invitados
def generar_clave_invitado(request):
    empresa = request.user.perfil.empresa
    if request.method == 'POST':
        GuestKey.objects.filter(empresa=empresa).delete()
        raw_key = secrets.token_urlsafe(24)
        GuestKey.objects.create(
            empresa=empresa,
            created_by=request.user,
            key=raw_key,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        messages.success(request, 'Clave de invitado generada. Vence en 10 minutos.')
    return redirect('dashboard')


def nosotros(request):
    return render(request, 'inventory/nosotros.html')

@login_required(login_url='login')
def dashboard(request):
    perfil = request.user.perfil
    empresa = perfil.empresa

    productos = Producto.objects.filter(empresa=empresa)

    total_productos = productos.count()
    en_stock = productos.filter(stock_actual__gt=F('stock_minimo')).count()
    stock_bajo = productos.filter(stock_actual__gt=0, stock_actual__lte=F('stock_minimo')).count()
    sin_stock = productos.filter(stock_actual=0).count()

    productos_recientes = productos[:5]
    movimientos_recientes = MovimientoStock.objects.filter(empresa=empresa).select_related('producto')[:10]

    clave_activa = GuestKey.objects.filter(empresa=empresa, expires_at__gt=timezone.now()).order_by('-created_at').first()

    context = {
        'total_productos': total_productos,
        'en_stock': en_stock,
        'stock_bajo': stock_bajo,
        'sin_stock': sin_stock,
        'productos_recientes': productos_recientes,
        'movimientos_recientes': movimientos_recientes,
        'clave_activa': clave_activa,
        'clave_restante_seg': clave_activa.segundos_restantes if clave_activa else None,
    }
    return render(request, 'inventory/dashboard.html', context)


@login_required(login_url='login')
def producto_lista(request):
    perfil = request.user.perfil
    empresa = perfil.empresa
    query = request.GET.get('q', '').strip()
    cat_id = request.GET.get('categoria', '')
    op_ids = [x for x in request.GET.getlist('opcion') if x]
    estado = request.GET.get('estado', '')
    orden = request.GET.get('orden', '')

    productos = Producto.objects.filter(empresa=empresa).select_related('categoria')
    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) | Q(codigo_barras__icontains=query)
        )
    if cat_id:
        productos = productos.filter(categoria_id=cat_id)
    if op_ids:
        for op_id in op_ids:
            productos = productos.filter(opciones__id=op_id)
    if estado == 'en':
        productos = productos.filter(stock_actual__gt=F('stock_minimo'))
    elif estado == 'bajo':
        productos = productos.filter(stock_actual__gt=0, stock_actual__lte=F('stock_minimo'))
    elif estado == 'sin':
        productos = productos.filter(stock_actual=0)

    if orden == 'nombre':
        productos = productos.order_by('nombre')
    elif orden == 'precio':
        productos = productos.order_by('-precio_venta')
    elif orden == 'stock':
        productos = productos.order_by('-stock_actual')
    else:
        productos = productos.order_by('-id')

    categorias = Categoria.objects.filter(empresa=empresa)
    atributos = Atributo.objects.filter(empresa=empresa).prefetch_related('opciones')
    cat_seleccionada = int(cat_id) if cat_id else None
    ops_seleccionadas = [int(x) for x in op_ids]

    context = {
        'productos': productos.distinct(),
        'query': query,
        'categorias': categorias,
        'atributos': atributos,
        'cat_seleccionada': cat_seleccionada,
        'ops_seleccionadas': ops_seleccionadas,
        'estado': estado,
        'orden': orden,
    }
    return render(request, 'inventory/producto_lista.html', context)


@login_required(login_url='login')
@bloquear_invitados
def producto_agregar(request):
    perfil = request.user.perfil
    empresa = perfil.empresa
    categorias = Categoria.objects.filter(empresa=empresa)
    atributos = Atributo.objects.filter(empresa=empresa).prefetch_related('opciones')

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        codigo_barras = request.POST.get('codigo_barras', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        categoria_id = request.POST.get('categoria', '')
        precio_costo = _precio_o_error(request, request.POST.get('precio_costo', ''), 'costo')
        precio_venta = _precio_o_error(request, request.POST.get('precio_venta', ''), 'venta')
        if precio_costo is None or precio_venta is None:
            return render(request, 'inventory/producto_form.html', {
                'categorias': categorias, 'atributos': atributos,
            })
        stock_actual = request.POST.get('stock_actual', 0)
        stock_minimo = request.POST.get('stock_minimo', 5)
        opcion_ids = request.POST.getlist('opciones')

        if not nombre:
            messages.error(request, 'El nombre del producto es obligatorio.')
            return render(request, 'inventory/producto_form.html', {
                'categorias': categorias, 'atributos': atributos,
            })

        categoria = None
        if categoria_id:
            categoria = get_object_or_404(Categoria, pk=categoria_id, empresa=empresa)

        producto = Producto.objects.create(
            empresa=empresa,
            nombre=nombre,
            codigo_barras=codigo_barras or None,
            descripcion=descripcion,
            categoria=categoria,
            precio_costo=precio_costo,
            precio_venta=precio_venta,
            stock_actual=int(stock_actual),
            stock_minimo=int(stock_minimo),
        )

        opciones_validas = OpcionAtributo.objects.filter(
            atributo__empresa=empresa, pk__in=opcion_ids
        )
        producto.opciones.set(opciones_validas)

        messages.success(request, f'Producto "{nombre}" creado correctamente.')
        return redirect('producto_lista')

    return render(request, 'inventory/producto_form.html', {
        'categorias': categorias, 'atributos': atributos,
    })


@login_required(login_url='login')
@bloquear_invitados
def producto_editar(request, pk):
    perfil = request.user.perfil
    empresa = perfil.empresa
    producto = get_object_or_404(Producto, pk=pk, empresa=empresa)
    categorias = Categoria.objects.filter(empresa=empresa)
    atributos = Atributo.objects.filter(empresa=empresa).prefetch_related('opciones')

    if request.method == 'POST':
        producto.nombre = request.POST.get('nombre', '').strip()
        producto.codigo_barras = request.POST.get('codigo_barras', '').strip() or None
        producto.descripcion = request.POST.get('descripcion', '').strip()

        precio_costo = _precio_o_error(request, request.POST.get('precio_costo', ''), 'costo')
        precio_venta = _precio_o_error(request, request.POST.get('precio_venta', ''), 'venta')
        if precio_costo is None or precio_venta is None:
            return render(request, 'inventory/producto_form.html', {
                'producto': producto, 'categorias': categorias, 'atributos': atributos,
            })
        producto.precio_costo = precio_costo
        producto.precio_venta = precio_venta
        producto.stock_actual = int(request.POST.get('stock_actual', 0))
        producto.stock_minimo = int(request.POST.get('stock_minimo', 5))

        categoria_id = request.POST.get('categoria', '')
        if categoria_id:
            producto.categoria = get_object_or_404(Categoria, pk=categoria_id, empresa=empresa)
        else:
            producto.categoria = None

        if not producto.nombre:
            messages.error(request, 'El nombre del producto es obligatorio.')
            return render(request, 'inventory/producto_form.html', {
                'producto': producto, 'categorias': categorias, 'atributos': atributos,
            })

        producto.save()

        opcion_ids = request.POST.getlist('opciones')
        opciones_validas = OpcionAtributo.objects.filter(
            atributo__empresa=empresa, pk__in=opcion_ids
        )
        producto.opciones.set(opciones_validas)

        messages.success(request, f'Producto "{producto.nombre}" actualizado correctamente.')
        return redirect('producto_lista')

    opciones_actuales = set(producto.opciones.values_list('pk', flat=True))
    return render(request, 'inventory/producto_form.html', {
        'producto': producto, 'categorias': categorias, 'atributos': atributos,
        'opciones_actuales': opciones_actuales,
    })


@login_required(login_url='login')
@bloquear_invitados
def stock_movimiento(request, pk):
    perfil = request.user.perfil
    empresa = perfil.empresa
    producto = get_object_or_404(Producto, pk=pk, empresa=empresa)
    movimientos = MovimientoStock.objects.filter(producto=producto)[:10]

    if request.method == 'POST':
        tipo = request.POST.get('tipo', '')
        cantidad = request.POST.get('cantidad', '')
        motivo = request.POST.get('motivo', '').strip()

        if not tipo or not cantidad:
            messages.error(request, 'El tipo y la cantidad son obligatorios.')
            return render(request, 'inventory/stock_movimiento.html', {
                'producto': producto, 'movimientos': movimientos, 'tipo_seleccionado': tipo,
            })

        cantidad = int(cantidad)
        if tipo == MovimientoStock.TipoMovimiento.SALIDA and cantidad > producto.stock_actual:
            messages.error(request, f'Stock insuficiente. Solo hay {producto.stock_actual} unidades.')
            return render(request, 'inventory/stock_movimiento.html', {
                'producto': producto, 'movimientos': movimientos, 'tipo_seleccionado': tipo,
            })

        MovimientoStock.objects.create(
            empresa=empresa,
            producto=producto,
            usuario=request.user,
            tipo=tipo,
            cantidad=cantidad,
            motivo=motivo,
        )

        messages.success(request, f'Movimiento registrado. Stock actual: {producto.stock_actual}')
        return redirect('stock_movimiento', pk=producto.pk)

    return render(request, 'inventory/stock_movimiento.html', {
        'producto': producto, 'movimientos': movimientos,
    })


@login_required(login_url='login')
@bloquear_invitados
def stock_rapido(request, pk):
    perfil = request.user.perfil
    empresa = perfil.empresa
    producto = get_object_or_404(Producto, pk=pk, empresa=empresa)
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'vender':
            if producto.stock_actual <= 0:
                messages.error(request, f'"{producto.nombre}" sin stock disponible.')
            else:
                MovimientoStock.objects.create(
                    empresa=empresa, producto=producto, usuario=request.user,
                    tipo=MovimientoStock.TipoMovimiento.SALIDA,
                    cantidad=1, motivo='Venta rápida',
                )
                messages.success(request, f'Venta registrada: "{producto.nombre}". Stock: {producto.stock_actual}')
        elif accion == 'reponer':
            MovimientoStock.objects.create(
                empresa=empresa, producto=producto, usuario=request.user,
                tipo=MovimientoStock.TipoMovimiento.ENTRADA,
                cantidad=1, motivo='Reposición rápida',
            )
            messages.success(request, f'Reposición registrada: "{producto.nombre}". Stock: {producto.stock_actual}')
    return redirect('producto_lista')


@login_required(login_url='login')
def categoria_lista(request):
    perfil = request.user.perfil
    empresa = perfil.empresa
    categorias = Categoria.objects.filter(empresa=empresa).annotate(cantidad_productos=Count('productos'))
    return render(request, 'inventory/categoria_lista.html', {'categorias': categorias})


@login_required(login_url='login')
def categoria_agregar(request):
    perfil = request.user.perfil
    empresa = perfil.empresa

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()

        if not nombre:
            messages.error(request, 'El nombre de la categoría es obligatorio.')
            return render(request, 'inventory/categoria_form.html')

        if Categoria.objects.filter(empresa=empresa, nombre__iexact=nombre).exists():
            messages.error(request, f'La categoría "{nombre}" ya existe.')
            return render(request, 'inventory/categoria_form.html')

        Categoria.objects.create(empresa=empresa, nombre=nombre, descripcion=descripcion)
        messages.success(request, f'Categoría "{nombre}" creada correctamente.')
        return redirect('categoria_lista')

    return render(request, 'inventory/categoria_form.html')


@login_required(login_url='login')
@bloquear_invitados
def categoria_eliminar(request, pk):
    perfil = request.user.perfil
    empresa = perfil.empresa
    categoria = get_object_or_404(Categoria, pk=pk, empresa=empresa)

    if request.method == 'POST':
        nombre = categoria.nombre
        categoria.delete()
        messages.success(request, f'Categoría "{nombre}" eliminada.')
        return redirect('categoria_lista')

    return render(request, 'inventory/categoria_eliminar.html', {'categoria': categoria})


@login_required(login_url='login')
def atributo_lista(request):
    perfil = request.user.perfil
    empresa = perfil.empresa
    atributos = Atributo.objects.filter(empresa=empresa).annotate(
        cantidad_opciones=Count('opciones'),
        cantidad_productos=Count('opciones__productos'),
    )
    return render(request, 'inventory/atributo_lista.html', {'atributos': atributos})


@login_required(login_url='login')
def atributo_agregar(request):
    perfil = request.user.perfil
    empresa = perfil.empresa

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()

        if not nombre:
            messages.error(request, 'El nombre del atributo es obligatorio.')
            return render(request, 'inventory/atributo_form.html')

        if Atributo.objects.filter(empresa=empresa, nombre__iexact=nombre).exists():
            messages.error(request, f'El atributo "{nombre}" ya existe.')
            return render(request, 'inventory/atributo_form.html')

        atributo = Atributo.objects.create(empresa=empresa, nombre=nombre)

        opciones_raw = request.POST.getlist('opcion')
        for valor in opciones_raw:
            valor = valor.strip()
            if valor:
                OpcionAtributo.objects.create(atributo=atributo, valor=valor)

        messages.success(request, f'Atributo "{nombre}" creado correctamente.')
        return redirect('atributo_lista')

    return render(request, 'inventory/atributo_form.html')


@login_required(login_url='login')
@bloquear_invitados
def atributo_editar(request, pk):
    perfil = request.user.perfil
    empresa = perfil.empresa
    atributo = get_object_or_404(Atributo, pk=pk, empresa=empresa)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()

        if not nombre:
            messages.error(request, 'El nombre del atributo es obligatorio.')
            return render(request, 'inventory/atributo_form.html', {'atributo': atributo})

        if Atributo.objects.filter(empresa=empresa, nombre__iexact=nombre).exclude(pk=pk).exists():
            messages.error(request, f'El atributo "{nombre}" ya existe.')
            return render(request, 'inventory/atributo_form.html', {'atributo': atributo})

        atributo.nombre = nombre
        atributo.save()

        opcion_ids_existentes = [int(x) for x in request.POST.getlist('opcion_ids')]
        opciones_raw = request.POST.getlist('opcion')
        nuevas_opciones = []
        for valor in opciones_raw:
            valor = valor.strip()
            if valor:
                op, _ = OpcionAtributo.objects.get_or_create(atributo=atributo, valor=valor)
                nuevas_opciones.append(op.pk)

        atributo.opciones.exclude(pk__in=nuevas_opciones).delete()

        messages.success(request, f'Atributo "{nombre}" actualizado correctamente.')
        return redirect('atributo_lista')

    opciones = atributo.opciones.all()
    return render(request, 'inventory/atributo_form.html', {'atributo': atributo, 'opciones': opciones})


@login_required(login_url='login')
@bloquear_invitados
def atributo_eliminar(request, pk):
    perfil = request.user.perfil
    empresa = perfil.empresa
    atributo = get_object_or_404(Atributo, pk=pk, empresa=empresa)

    if request.method == 'POST':
        nombre = atributo.nombre
        atributo.delete()
        messages.success(request, f'Atributo "{nombre}" eliminado.')
        return redirect('atributo_lista')

    return render(request, 'inventory/atributo_eliminar.html', {'atributo': atributo})
