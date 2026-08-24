from django.contrib import admin
from .models import (
    Empresa, PerfilUsuario, Categoria, Atributo, OpcionAtributo,
    Producto, MovimientoStock, GuestKey,
)


class OpcionAtributoInline(admin.TabularInline):
    model = OpcionAtributo
    extra = 1


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'cuit_o_id', 'activa', 'created_at']
    list_filter = ['activa']
    search_fields = ['nombre', 'cuit_o_id']


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ['user', 'empresa', 'rol']
    list_filter = ['rol', 'empresa']


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'empresa']
    list_filter = ['empresa']
    search_fields = ['nombre']


@admin.register(Atributo)
class AtributoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'empresa']
    list_filter = ['empresa']
    search_fields = ['nombre']
    inlines = [OpcionAtributoInline]


@admin.register(OpcionAtributo)
class OpcionAtributoAdmin(admin.ModelAdmin):
    list_display = ['atributo', 'valor', 'get_empresa']
    list_filter = ['atributo__empresa']

    def get_empresa(self, obj):
        return obj.atributo.empresa.nombre
    get_empresa.short_description = 'Empresa'


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'codigo_barras', 'categoria', 'empresa', 'stock_actual', 'precio_venta', 'stock_minimo']
    list_filter = ['empresa', 'categoria']
    search_fields = ['nombre', 'codigo_barras']
    filter_horizontal = ['opciones']

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        obj.save()


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display = ['producto', 'tipo', 'cantidad', 'motivo', 'usuario', 'empresa', 'fecha']
    list_filter = ['tipo', 'empresa']
    readonly_fields = ['fecha']


@admin.register(GuestKey)
class GuestKeyAdmin(admin.ModelAdmin):
    list_display = ['key', 'empresa', 'created_by', 'created_at', 'expires_at', 'es_valida']
    list_filter = ['empresa']
    search_fields = ['key']
    readonly_fields = ['created_at']
