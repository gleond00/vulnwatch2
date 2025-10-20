#!/bin/bash

# Servidor: propiedad y permisos a www-data, usuario que utiliza Apache2.
chown -R www-data:www-data /vulnwatch2
#chown -R www-data:www-data /geah-axon
#chown -R www-data:www-data /geah-static
#chown -R www-data:www-data /geah-media
#chown -R www-data:www-data /geah-private
#chown -R www-data:www-data /geah-tmp
# chown -R www-data:www-data /geah_volcado
chmod -R 700 /vulnwatch2
#chmod -R 700 /geah-axon
#chmod -R 700 /geah-static
#chmod -R 700 /geah-media
#chmod -R 700 /geah-private
#chmod -R 700 /geah-tmp
# No sé por qué este no: chmod -R 700 /geah_varios
# chmod -R 700 /geah_volcado

# Bibliotecas python3: permisos de lectura y ejecución a todos, para que www-data pueda utilizarla.
# chmod -R 755 /usr/local/lib/python2.7/dist-packages/ipap
#chmod -R 755 /usr/local/lib/python3.11/dist-packages
