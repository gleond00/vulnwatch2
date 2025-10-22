(function() {
  // Ejecuta tras cargar el admin
  function ready(fn){ if(document.readyState!='loading'){ fn(); } else { document.addEventListener('DOMContentLoaded', fn); } }

  ready(function(){
    // Busca cabeceras de tablas dentro de grupos inline
    var groups = document.querySelectorAll('.inline-group table');
    if (!groups || !groups.length) return;

    // Valor actual del parámetro de orden
    var url = new URL(window.location.href);
    var params = url.searchParams;
    var current = (params.get('issues_order') || 'updated').toLowerCase();

    groups.forEach(function(tbl){
      var ths = tbl.querySelectorAll('thead th');
      if (!ths || !ths.length) return;
      ths.forEach(function(th){
        var label = (th.textContent || '').trim();
        if (label === 'Vuln') {
          th.style.cursor = 'pointer';
          th.title = current === 'vuln' ? 'Ordenar por últimas actualizaciones' : 'Ordenar por vulnerabilidad';

          // Indicador visual mínimo (no altera layout)
          try {
            var mark = document.createElement('span');
            mark.style.fontSize = '11px';
            mark.style.marginLeft = '6px';
            mark.style.opacity = '0.7';
            mark.textContent = current === 'vuln' ? '▲' : '↕';
            th.appendChild(mark);
          } catch(e){}

          th.addEventListener('click', function(){
            var now = (params.get('issues_order') || 'updated').toLowerCase();
            if (now === 'vuln') { params.set('issues_order', 'updated'); }
            else { params.set('issues_order', 'vuln'); }
            url.search = params.toString();
            window.location.href = url.toString();
          });
        }
      });
    });
  });
})();
