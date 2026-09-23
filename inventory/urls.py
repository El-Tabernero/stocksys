from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('invitado/', views.invitado, name='invitado'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reportes/', views.reporte, name='reporte'),
    path('dashboard/generar-clave-invitado/', views.generar_clave_invitado, name='generar_clave_invitado'),
    path('nosotros/', views.nosotros, name='nosotros'),
    path('productos/', views.producto_lista, name='producto_lista'),
    path('productos/agregar/', views.producto_agregar, name='producto_agregar'),
    path('productos/<int:pk>/editar/', views.producto_editar, name='producto_editar'),
    path('productos/<int:pk>/stock/', views.stock_movimiento, name='stock_movimiento'),
    path('productos/<int:pk>/stock-rapido/', views.stock_rapido, name='stock_rapido'),
    path('categorias/', views.categoria_lista, name='categoria_lista'),
    path('categorias/agregar/', views.categoria_agregar, name='categoria_agregar'),
    path('categorias/<int:pk>/eliminar/', views.categoria_eliminar, name='categoria_eliminar'),
    path('atributos/', views.atributo_lista, name='atributo_lista'),
    path('atributos/agregar/', views.atributo_agregar, name='atributo_agregar'),
    path('atributos/<int:pk>/editar/', views.atributo_editar, name='atributo_editar'),
    path('atributos/<int:pk>/eliminar/', views.atributo_eliminar, name='atributo_eliminar'),
]
