from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import F, Q, Count
from .models import Empresa, PerfilUsuario, Categoria, Producto, MovimientoStock


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

    context = {
        'total_productos': total_productos,
        'en_stock': en_stock,
        'stock_bajo': stock_bajo,
        'sin_stock': sin_stock,
        'productos_recientes': productos_recientes,
        'movimientos_recientes': movimientos_recientes,
    }
    return render(request, 'inventory/dashboard.html', context)


@login_required(login_url='login')
def producto_lista(request):
    perfil = request.user.perfil
    empresa = perfil.empresa
    query = request.GET.get('q', '').strip()
    cat_id = request.GET.get('categoria', '')

    productos = Producto.objects.filter(empresa=empresa).select_related('categoria')
    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) | Q(codigo_barras__icontains=query)
        )
    if cat_id:
        productos = productos.filter(categoria_id=cat_id)

    categorias = Categoria.objects.filter(empresa=empresa)
    cat_seleccionada = int(cat_id) if cat_id else None

    context = {
        'productos': productos,
        'query': query,
        'categorias': categorias,
        'cat_seleccionada': cat_seleccionada,
    }
    return render(request, 'inventory/producto_lista.html', context)


@login_required(login_url='login')
def producto_agregar(request):
    perfil = request.user.perfil
    empresa = perfil.empresa
    categorias = Categoria.objects.filter(empresa=empresa)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        codigo_barras = request.POST.get('codigo_barras', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        categoria_id = request.POST.get('categoria', '')
        precio_costo = request.POST.get('precio_costo', 0)
        precio_venta = request.POST.get('precio_venta', 0)
        stock_actual = request.POST.get('stock_actual', 0)
        stock_minimo = request.POST.get('stock_minimo', 5)

        if not nombre:
            messages.error(request, 'El nombre del producto es obligatorio.')
            return render(request, 'inventory/producto_form.html', {'categorias': categorias})

        categoria = None
        if categoria_id:
            categoria = get_object_or_404(Categoria, pk=categoria_id, empresa=empresa)

        Producto.objects.create(
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
        messages.success(request, f'Producto "{nombre}" creado correctamente.')
        return redirect('producto_lista')

    return render(request, 'inventory/producto_form.html', {'categorias': categorias})


@login_required(login_url='login')
def producto_editar(request, pk):
    perfil = request.user.perfil
    empresa = perfil.empresa
    producto = get_object_or_404(Producto, pk=pk, empresa=empresa)
    categorias = Categoria.objects.filter(empresa=empresa)

    if request.method == 'POST':
        producto.nombre = request.POST.get('nombre', '').strip()
        producto.codigo_barras = request.POST.get('codigo_barras', '').strip() or None
        producto.descripcion = request.POST.get('descripcion', '').strip()
        producto.precio_costo = request.POST.get('precio_costo', 0)
        producto.precio_venta = request.POST.get('precio_venta', 0)
        producto.stock_actual = int(request.POST.get('stock_actual', 0))
        producto.stock_minimo = int(request.POST.get('stock_minimo', 5))

        categoria_id = request.POST.get('categoria', '')
        if categoria_id:
            producto.categoria = get_object_or_404(Categoria, pk=categoria_id, empresa=empresa)
        else:
            producto.categoria = None

        if not producto.nombre:
            messages.error(request, 'El nombre del producto es obligatorio.')
            return render(request, 'inventory/producto_form.html', {'producto': producto, 'categorias': categorias})

        producto.save()
        messages.success(request, f'Producto "{producto.nombre}" actualizado correctamente.')
        return redirect('producto_lista')

    return render(request, 'inventory/producto_form.html', {'producto': producto, 'categorias': categorias})


@login_required(login_url='login')
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
