"""Agregación, mensaje, regla 21:00 y Matplotlib deterministas."""
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from textwrap import fill
from zoneinfo import ZoneInfo
from alertas_operacionales import normalizar_estado, es_wip
from corte_operacional import ConfiguracionCorte
from fuente_operacional import utc_iso

TIPOS=('Incident','Service Request')
ACTIVOS=('Pendiente','Abierto','Work in Progress')
NOMBRES={'PENDIENTE':'Pendiente','ABIERTO':'Abierto','WORK_IN_PROGRESS':'Work in Progress',
         'CERRADO':'Cerrado','CANCELADO':'Cancelado','RESUELTO':'Resuelto','ESCALADO':'Escalado'}


def validar_corte_2100(corte):
    utc_iso(corte)
    local=corte.astimezone(ZoneInfo(ConfiguracionCorte().zona))
    if local.timetz().replace(tzinfo=None)!=time(21,0):
        raise ValueError('El reporte requiere exactamente las 21:00 America/Santiago')
    return local


@dataclass(frozen=True)
class ResumenOperacional:
    instantanea: object
    componentes: tuple  # (componente, Incident, Service Request)
    estados: tuple     # (estado activo, Incident, Service Request)
    conteos_todos: tuple  # (tipo, estado normalizado legible, cantidad)
    wip: tuple

    @property
    def activos(self): return sum(i+s for _,i,s in self.estados)

    def datos(self):
        return {'fuente':self.instantanea.fuente,'corte':utc_iso(self.instantanea.corte),
            'corte_santiago':validar_corte_2100(self.instantanea.corte).isoformat(),
            'hash_instantanea':self.instantanea.hash_contenido,'leidos':len(self.instantanea.tickets),
            'activos':self.activos,
            'por_componente':[dict(componente=c,Incident=i,**{'Service Request':s}) for c,i,s in self.componentes],
            'por_estado':[dict(estado=e,Incident=i,**{'Service Request':s}) for e,i,s in self.estados],
            'conteos_por_tipo_estado':[{'tipo':t,'estado':e,'cantidad':n} for t,e,n in self.conteos_todos],
            'tickets_wip':[{'numero_ticket':t.numero_ticket,'estado_observado':t.estado} for t in self.wip]}


def agregar(snapshot):
    componentes={}
    estados={e:{t:0 for t in TIPOS} for e in ACTIVOS}
    todos={(t,e):0 for t in TIPOS for e in ('Cerrado','Abierto','Pendiente','Cancelado','Work in Progress')}
    wip=[]
    for ticket in snapshot.tickets:
        if ticket.tipo_ticket not in TIPOS:
            raise ValueError('Tipo operacional no reconocido')
        estado=NOMBRES.get(normalizar_estado(ticket.estado))
        if estado is None: raise ValueError('Estado fuera del contrato y compatibilidad histórica')
        if not isinstance(ticket.componente,str) or not ticket.componente.strip():
            raise ValueError('Componente operacional no informado')
        todos[(ticket.tipo_ticket,estado)]=todos.get((ticket.tipo_ticket,estado),0)+1
        if estado in ACTIVOS:
            componentes.setdefault(ticket.componente,{t:0 for t in TIPOS})[ticket.tipo_ticket]+=1
            estados[estado][ticket.tipo_ticket]+=1
        if es_wip(ticket.estado): wip.append(ticket)
    return ResumenOperacional(snapshot,
        tuple((c,v[TIPOS[0]],v[TIPOS[1]]) for c,v in sorted(componentes.items())),
        tuple((e,estados[e][TIPOS[0]],estados[e][TIPOS[1]]) for e in ACTIVOS),
        tuple((t,e,n) for (t,e),n in sorted(todos.items())),tuple(wip))


def evaluar_alertas_2100(resumen):
    corte=validar_corte_2100(resumen.instantanea.corte)
    return tuple({'numero_ticket':t.numero_ticket,'codigo_regla':'WIP_EN_RESUMEN_2100',
                  'fecha_corte':utc_iso(corte),'estado_observado':t.estado}
                 for t in resumen.wip)


def generar_mensaje(resumen):
    validar_corte_2100(resumen.instantanea.corte)
    counts={e:(i,s) for e,i,s in resumen.estados}
    if resumen.wip:
        observacion=('Se detectan tickets Work in Progress al corte de las 21:00: '+
                     ', '.join(t.numero_ticket for t in resumen.wip)+'. Se registra evidencia de incumplimiento sin modificar tickets.')
    else:
        observacion='No se detectan tickets Work in Progress al corte de las 21:00.'
    return ('Estimados, buenas noches.\n\n'
        'Se adjunta el estado operacional de la mina, con el gráfico de distribución por componentes y conteo de incidentes y requerimientos.\n\n'
        f'Corte: {validar_corte_2100(resumen.instantanea.corte).isoformat()} (America/Santiago).\n\n'
        f'Resumen de incidentes:\nPendientes: {counts["Pendiente"][0]}\nAbiertos: {counts["Abierto"][0]}\nWork in Progress: {counts["Work in Progress"][0]}\n\n'
        f'Resumen de requerimientos:\nPendientes: {counts["Pendiente"][1]}\nAbiertos: {counts["Abierto"][1]}\nWork in Progress: {counts["Work in Progress"][1]}\n\n'
        f'Observaciones:\n{observacion}\n\nSaludos,\nMesa de Ayuda.\n')


def construir_figura(resumen):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.ticker import MaxNLocator
    validar_corte_2100(resumen.instantanea.corte)
    width=max(13,min(32,2.2*len(resumen.componentes)))
    fig,axes=plt.subplots(2,1,figsize=(width,10),layout='constrained')
    colores=('#ee7667','#4287c7')
    for ax,rows,title in ((axes[0],resumen.componentes,'Distribución de Tickets por Incidentes y Requerimientos.'),
                          (axes[1],resumen.estados,'Estados operacionales de tickets activos')):
        x=list(range(len(rows)))
        bars=[]
        for j,tipo in enumerate(TIPOS):
            b=ax.bar([v+(-.19 if j==0 else .19) for v in x],[r[j+1] for r in rows],
                     width=.36,label=tipo,color=colores[j],zorder=3)
            ax.bar_label(b,padding=3,fontsize=10)
            bars.append(b)
        ax.set_xticks(x,[fill(r[0],20) for r in rows],fontsize=11)
        ax.set_ylabel('Cantidad de tickets',fontsize=11)
        ax.set_title(title,fontsize=16,fontweight='bold',pad=16)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.grid(axis='y',alpha=.22,zorder=0)
        ax.spines[['top','right']].set_visible(False)
        ymax=max((max(r[1:]) for r in rows),default=0)
        ax.set_ylim(0,max(1,ymax*1.25+0.5))
        ax.legend(loc='upper right',frameon=False)
        if not rows: ax.text(.5,.45,'Sin tickets activos',ha='center',va='center',transform=ax.transAxes,fontsize=14)
    axes[0].set_xlabel('Componente o tipo de solicitud')
    for container in axes[1].containers:
        container[2].set_edgecolor('#bd1f2d'); container[2].set_linewidth(2.5)
        container[2].set_hatch('///')
    axes[1].get_xticklabels()[2].set_color('#bd1f2d')
    axes[1].get_xticklabels()[2].set_fontweight('bold')
    handles,labels=axes[1].get_legend_handles_labels()
    axes[1].legend(handles+[Patch(facecolor='white',edgecolor='#bd1f2d',hatch='///')],
                   labels+['WIP: incumplimiento de entrega'],loc='upper right',frameon=False)
    fig.suptitle('Minera Galaxy · Reporte operacional de las 21:00\n'+
                 validar_corte_2100(resumen.instantanea.corte).strftime('%d-%m-%Y · America/Santiago')+
                 f' · {resumen.activos} tickets activos',fontsize=18,fontweight='bold')
    return fig


def generar_grafico(resumen,path):
    fig=construir_figura(resumen)
    import matplotlib.pyplot as plt
    try: fig.savefig(Path(path),dpi=145,metadata={'Software':'Minera Galaxy - Matplotlib'})
    finally: plt.close(fig)
