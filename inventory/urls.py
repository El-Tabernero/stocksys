from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('productos/', views.producto_lista, name='producto_lista'),
    path('productos/agregar/', views.producto_agregar, name='producto_agregar'),
    path('productos/<int:pk>/editar/', views.producto_editar, name='producto_editar'),
    path('productos/<int:pk>/stock/', views.stock_movimiento, name='stock_movimiento'),
    path('categorias/', views.categoria_lista, name='categoria_lista'),
    path('categorias/agregar/', views.categoria_agregar, name='categoria_agregar'),
    path('categorias/<int:pk>/eliminar/', views.categoria_eliminar, name='categoria_eliminar'),
]
