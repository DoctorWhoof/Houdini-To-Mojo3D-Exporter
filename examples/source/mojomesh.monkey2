Namespace mojogame

#Import "<std>"
#Import "<mojo>"
#Import "<mojo3d>"

Using std..
Using mojo..
Using mojo3d..


Function LoadJsonModel:Model( filepath:String )
	
	Local json := JsonObject.Load( filepath )
	Local mesh := New Mesh
	
	
	Local verts := New Stack<Vec3f>
	Local v := json["verts"].ToArray()
	For Local i := 0 Until v.Length Step 3
		verts.Add( New Vec3f( v[i].ToNumber(), v[i+1].ToNumber(), v[i+2].ToNumber() ) )
	Next
	
	
	Local normals := New Stack<Vec3f>
	Local n := json["normals"].ToArray()
	For Local i := 0 Until n.Length Step 3
		normals.Add( New Vec3f( n[i].ToNumber(), n[i+1].ToNumber(), n[i+2].ToNumber() ) )
	Next
	
	
	Local colors := New Stack<Color>
	Local c := json["colors"].ToArray()
	For Local i := 0 Until c.Length Step 3
		colors.Add( New Color( c[i+2].ToNumber(), c[i+1].ToNumber(), c[i].ToNumber() ) )
	Next
	
	
	Local uv0 := New Stack<Vec2f>
	Local t := json["uv0"].ToArray()
	For Local i := 0 Until t.Length Step 2
		uv0.Add( New Vec2f( t[i].ToNumber(), t[i+1].ToNumber() ) )
	Next
	
	
	Local vertices := New Stack<Vertex3f>
	For Local n := 0 Until verts.Length
		Local normal := New Vec3f
		Local uv := New Vec2f
		Local color := std.graphics.Color.White
		
		If normals.Length Then normal = normals[n]
		If uv0.Length Then uv = uv0[n]
		If colors.Length Then color = colors[n]
		
		Local  vert := New Vertex3f( verts[n].X, verts[n].Y, verts[n].Z, uv.X, uv.Y, normal.X, normal.Y, normal.Z )
		vert.color = color.ToARGB()
		mesh.AddVertex( vert )
	Next


	Local groups := json["triangles"].ToObject()
	For Local value := Eachin groups.Values
		mesh.AddMaterials( 1 )
		Local g := value.ToArray()
		For Local n := 0 Until g.Length Step 3
			mesh.AddTriangle( g[n].ToNumber(), g[n+1].ToNumber(), g[n+2].ToNumber(), mesh.NumMaterials-1 )
		Next
	Next
	
	mesh.FlipTriangles()
	If normals.Length < 1
		mesh.UpdateTangents()
		mesh.UpdateNormals()
	End
	mesh.Compact()
	
	Local materials := New Stack<PbrMaterial>
	If json["materials"]
		Local mDict := json["materials"].ToObject()
		If mDict.Count()
			For Local name := Eachin mDict.Keys
				Local newMat := New PbrMaterial
				Local mat := mDict[name].ToObject()
				If mat["ColorFactor"] Then newMat.ColorFactor = JsonToColor(mat["ColorFactor"])
				If mat["MetalnessFactor"] Then newMat.MetalnessFactor = JsonToFloat(mat["MetalnessFactor"])
				If mat["RoughnessFactor"] Then newMat.RoughnessFactor = JsonToFloat(mat["RoughnessFactor"])
				If mat["ColorTexture"] Then newMat.ColorTexture = JsonToTexture(mat["ColorTexture"])
				If mat["RoughnessTexture"] Then newMat.RoughnessTexture = JsonToTexture(mat["RoughnessTexture"])
				If mat["MetalnessTexture"] Then newMat.MetalnessTexture = JsonToTexture(mat["MetalnessTexture"])
				If mat["EmissiveTexture"] Then newMat.EmissiveTexture = JsonToTexture(mat["EmissiveTexture"])
				If mat["NormalTexture"] Then newMat.NormalTexture = JsonToTexture(mat["NormalTexture"])
				materials.Push( newMat )
			Next
		End
	Else
		For Local n := 0 Until mesh.NumMaterials
			materials.Push( New PbrMaterial( std.graphics.Color.White * Rnd(0.5,1.0), 0, 0.5 ) )
		Next
	End
	
	
	Local model := New Model
	Local mats := New Material[materials.Length]
	
	
	For Local i := 0 Until materials.Length
		mats[i] = materials[i]
	Next
	
	model.Mesh = mesh
	model.Materials = mats
	Return model
End

Private

Function JsonToFloat:Float( json:JsonValue )
	If json.IsNumber
		Return Float( json.ToNumber() )
	End
	Return Null
End


Function JsonToColor:Color( json:JsonValue )
	If json.IsArray
		Local data := json.ToArray()
		If data.Length > 2 And data.Length < 5
			Local alpha := 1.0
			If data.Length > 3 Then alpha = data[3].ToNumber()
			Local color	:= New Color( data[0].ToNumber(), data[1].ToNumber(), data[2].ToNumber(), alpha )
			Return color
		End
	End
	Return Null
End


Function JsonToTexture:Texture( json:JsonValue, flags:TextureFlags = TextureFlags.FilterMipmap | TextureFlags.WrapST )
	If json.IsString
		Local texture := Texture.Load( json.ToString(), flags )
		Assert( texture, "JsonValue: Can't find texture path " + json.ToString() )
 			Return texture
	End
	Return Null
End
		

