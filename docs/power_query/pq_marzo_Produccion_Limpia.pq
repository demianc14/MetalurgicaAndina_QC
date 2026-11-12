// Extraído del .pbix con código (pbixray). La URL de OneDrive se reemplazó por <OneDrive>.
// Produccion_Limpia
let
  Origen = Excel.Workbook(Web.Contents("<OneDrive>/IIN2002_PQ_Datos_Produccion_Sucio-4D2L.xlsx"), null, true),
  #"Navegación 1" = Origen{[Item = "tbl_Produccion_Sucia", Kind = "Table"]}[Data],
  #"Texto recortado Linea" = Table.TransformColumns(#"Navegación 1", {{"Linea_Produccion", each Text.Trim(_), type nullable text}}),
  #"Mayúsculas aplicadas en cada palabra Linea_Prod" = Table.TransformColumns(#"Texto recortado Linea", {{"Linea_Produccion", each Text.Proper(Text.From(_)), type nullable text}}),
  #"Valor reemplazado Linea" = Table.ReplaceValue(#"Mayúsculas aplicadas en cada palabra Linea_Prod", "Linea", "Línea", Replacer.ReplaceText, {"Linea_Produccion"}),
  #"Texto recortado Turno" = Table.TransformColumns(#"Valor reemplazado Linea", {{"Turno", each Text.Trim(Text.From(_)), type nullable text}}),
  #"Mayúsculas aplicadas en cada palabra Turno" = Table.TransformColumns(#"Texto recortado Turno", {{"Turno", each Text.Proper(_), type nullable text}}),
  #"Texto recortado SKU" = Table.TransformColumns(#"Mayúsculas aplicadas en cada palabra Turno", {{"SKU", each Text.Trim(Text.From(_)), type nullable text}}),
  #"Tipo de columna cambiado" = Table.TransformColumnTypes(#"Texto recortado SKU", {{"Cantidad_Producida", type text}}),
  #"Texto recortado" = Table.TransformColumns(#"Tipo de columna cambiado", {{"Cantidad_Producida", each Text.Trim(_), type nullable text}}),
  // 5 vacíos de Tiempo_Paro_Min se dejan en null; no hay confirmación de que sean 0
  #"Tipo de columna cambiado Varias Variables" = Table.TransformColumnTypes(#"Texto recortado", {{"Cantidad_Producida", Int64.Type}, {"ID_Registro", Int64.Type}, {"Tiempo_Paro_Min", Int64.Type}, {"Unidades_Defectuosas", Int64.Type}, {"Fecha", type text}}),
  #"Columna condicional insertada" = Table.AddColumn(#"Tipo de columna cambiado Varias Variables", "Formato_Detectado", each if Text.Contains([Fecha], "/") then "SLASH" else if Text.StartsWith([Fecha], "2026-") then "ISO" else "MMM"),
  #"Personalizado agregado" = Table.AddColumn(#"Columna condicional insertada", "Token1", each if [Formato_Detectado] = "SLASH" then Number.FromText(Text.Start([Fecha], 2)) else null),
  #"Personalizado agregado 1" = Table.AddColumn(#"Personalizado agregado", "Token2", each if [Formato_Detectado] = "SLASH" then Number.FromText(Text.Middle([Fecha], 3, 2)) else
null),
  #"Personalizado agregado 2" = Table.AddColumn(#"Personalizado agregado 1", "Anio", each if [Formato_Detectado] = "SLASH" then Number.FromText(Text.End([Fecha], 4)) else null),
  #"Personalizado agregado 3" = Table.AddColumn(#"Personalizado agregado 2", "Fecha_Limpia", each if [Formato_Detectado] = "SLASH" then
(if ([Token1] = 3 or [Token1] = 4) and ([Token2] = 3 or [Token2] = 4) then null
else if [Token2] = 3 or [Token2] = 4 then #date([Anio], [Token2], [Token1])
else #date([Anio], [Token1], [Token2]))
else if [Formato_Detectado] = "ISO" then Date.FromText([Fecha])
else Date.FromText([Fecha], [Format = "dd-MMM-yy", Culture = "en-US"])),
  #"Columnas con nombre cambiado" = Table.RenameColumns(#"Personalizado agregado 3", {{"Fecha", "Fecha_Original"}, {"Fecha_Limpia", "Fecha"}}),
  #"Personalizado agregado 4" = Table.AddColumn(#"Columnas con nombre cambiado", "Estado_Fecha", each if [Fecha] = null then "REVISAR CON SUPERVISOR" else "OK"),
  #"Duplicados quitados" = Table.Distinct(#"Personalizado agregado 4", {"ID_Registro", "Fecha_Original", "Linea_Produccion", "Turno", "SKU", "Cantidad_Producida", "Unidades_Defectuosas", "Tiempo_Paro_Min", "Formato_Detectado", "Token1", "Token2", "Anio", "Fecha", "Estado_Fecha"}),
  #"Consultas combinadas" = Table.NestedJoin(#"Duplicados quitados", {"ID_Registro"}, Correcciones_Turno, {"ID_Registro"}, "Correcciones_Turno", JoinKind.LeftOuter),
  #"Correcciones_Turno expandido" = Table.ExpandTableColumn(#"Consultas combinadas", "Correcciones_Turno", {"Turno_Confirmado"}, {"Correcciones_Turno.Turno_Confirmado"}),
  #"Columnas con nombre cambiado 1" = Table.RenameColumns(#"Correcciones_Turno expandido", {{"Correcciones_Turno.Turno_Confirmado", "Turno_Confirmado"}}),
  #"Personalizado agregado 5" = Table.AddColumn(#"Columnas con nombre cambiado 1", "Turno_Final", each if [Turno] = null then [Turno_Confirmado] else [Turno]),
  #"Columnas con nombre cambiado 2" = Table.RenameColumns(#"Personalizado agregado 5", {{"Turno", "Turno_Original"}, {"Turno_Final", "Turno"}}),
  #"Consultas combinadas 1" = Table.NestedJoin(#"Columnas con nombre cambiado 2", {"SKU"}, Catalogo, {"SKU"}, "Catalogo", JoinKind.LeftOuter),
  #"Catalogo expandido" = Table.ExpandTableColumn(#"Consultas combinadas 1", "Catalogo", {"Producto", "Categoria", "Costo_Unitario_USD"}, {"Producto", "Categoria", "Costo_Unitario_USD"}),
  #"Tipo de columna cambiado 1" = Table.TransformColumnTypes(#"Catalogo expandido", {{"Costo_Unitario_USD", type number}}),
  #"Multiplicación insertada" = Table.AddColumn(#"Tipo de columna cambiado 1", "Multiplicación", each [Costo_Unitario_USD] * [Cantidad_Producida], type number),
  #"División insertada" = Table.AddColumn(#"Multiplicación insertada", "División", each [Unidades_Defectuosas] / [Cantidad_Producida], type number),
  #"Columnas con nombre cambiado 3" = Table.RenameColumns(#"División insertada", {{"Multiplicación", "Costo_Total_Producido"}}),
  #"Tipo de columna cambiado 2" = Table.TransformColumnTypes(#"Columnas con nombre cambiado 3", {{"Costo_Total_Producido", type number}}),
  #"Columnas con nombre cambiado 4" = Table.RenameColumns(#"Tipo de columna cambiado 2", {{"División", "Pct_Defectuosos"}}),
  #"Tipo de columna cambiado 3" = Table.TransformColumnTypes(#"Columnas con nombre cambiado 4", {{"Pct_Defectuosos", Percentage.Type}, {"Costo_Unitario_USD", Currency.Type}, {"Costo_Total_Producido", Currency.Type}}),
  #"Columna condicional insertada 1" = Table.AddColumn(#"Tipo de columna cambiado 3", "Estado_Calidad", each if [Pct_Defectuosos] <= 0.03 then "Cumple" else "No Cumple"),
  #"Columna condicional insertada 2" = Table.AddColumn(#"Columna condicional insertada 1", "Clasificación_Calidad", each if [Pct_Defectuosos] < 0.01 then "Excelente" else if [Pct_Defectuosos] <= 0.03 then "Aceptable" else "Crítico"),
  #"Columnas con nombre cambiado 5" = Table.RenameColumns(#"Columna condicional insertada 2", {{"Pct_Defectuosos", "Pct_Defectuosas"}}),
  #"Personalizado agregado 6" = Table.AddColumn(#"Columnas con nombre cambiado 5", "Turno_Problematico", each if [Pct_Defectuosas] > 0.03 and ([Tiempo_Paro_Min] ?? 0) > 30 then "Sí" else "No")
in
  #"Personalizado agregado 6"

// Catalogo
let
  Origen = Excel.Workbook(Web.Contents("<OneDrive>/IIN2002_PQ_Datos_Produccion_Sucio-4D2L.xlsx"), null, true),
  #"Navegación 1" = Origen{[Item = "tbl_Catalogo", Kind = "Table"]}[Data],
  #"Tipo de columna cambiado" = Table.TransformColumnTypes(#"Navegación 1", {{"SKU", type text}, {"Producto", type text}, {"Categoria", type text}, {"Costo_Unitario_USD", type number}, {"Precio_Venta_USD", type number}, {"Peso_kg", type number}}, "es")
in
  #"Tipo de columna cambiado"

// Correcciones_Turno
let
  Origen = Excel.Workbook(Web.Contents("<OneDrive>/IIN2002_PQ_Datos_Produccion_Sucio-4D2L.xlsx"), null, true),
  #"Navegación 1" = Origen{[Item = "tbl_Correcciones_Turno", Kind = "Table"]}[Data],
  #"Tipo de columna cambiado" = Table.TransformColumnTypes(#"Navegación 1", {{"ID_Registro", Int64.Type}, {"Turno_Confirmado", type text}}, "es")
in
  #"Tipo de columna cambiado"
