// Extraído del .pbix con código (pbixray). La URL de OneDrive se reemplazó por <OneDrive>.
// tbl_Prod
let
  Origen = Excel.Workbook(Web.Contents("<OneDrive>/Metalurgica Andina 3 Meses Consolidado.xlsx"), null, true),
  #"Navegación 1" = Origen{[Item = "tbl_Prod", Kind = "Table"]}[Data],
  #"Tipo de columna cambiado" = Table.TransformColumnTypes(#"Navegación 1", {{"ID_Registro", Int64.Type}, {"Fecha", type date}, {"línea_Produccion", type text}, {"Turno", type text}, {"SKU", type text}, {"Cantidad_Producida", Int64.Type}, {"Unidades_Defectuosas", Int64.Type}, {"Tiempo_Paro_Min", Int64.Type}, {"Categoria", type text}, {"Costo_Unitario", type number}, {"Costo_Total", type number}, {"% Defectuosos", type number}, {"Estado_Calidad (<3%_cumple)", type text}, {"Calidad_3_Niveles", type text}, {"Problematico", type text}}, "es")
in
  #"Tipo de columna cambiado"
