
# To do:

	#Exporting:
		# (?) Built in custom .mesh exporter, to bypass Houdini's file format limitations. The constructor will require importing the mesh loader in Monkey2.
		# (!) Self contained, full scene export: meshes without file nodes get exported IN the mojo3d file.
			#This can be incredibly inneficient if the users don't know what they're doing (redundant meshes, etc.). But it can be very powerful too!
			#Verts, faces and material groups are passed as Mesh contructor parameters
			#Materials should works "as is"?

	# Project folder location:
	#       .Exporter asks where the "assets" folder is, then assumes where everything goes (scenes, models, textures)
	#       .This will allow exporting of .mesh models at the same time as the scene!
	#       .It also allows checking for textures proper location. If not under the assets folder structure, they won't be readily available in the Monkey2 side!

	# (???) Auto-convert maps to pbr material if color texture path contains ".pbr"
	# Explore massive instancing (CopyToPoints, etc.). May need custom components in mojo3d.

#----------------------------------------------------------------------------

import json
import math
import os
import errno

convertLoadersToGlb = False
convertSaversToGlb = False
convertToAssetPaths = False
overrideMaterials = False
collapseHierachyOnLoad = False

jsondict = dict()       #main json file
orderedNodes = []       #final list, contains one json dictionary per valid node in the correct order
uniqueIDCounter = -1    #provides a global index for references (i.e. textures) before mojoID numbers are assigned

root = hou.node("/obj")
path = ""

#mojomesh globals
index = -1
vertsByPoint = dict()

#-------------------------------- Classes ----------------------------------

class mojonode:
	byHounode = dict()
	byPriority = dict()
	byReference = dict()    #Keys: all path references, to be replaced by mojo ids, Values:the correspondent mojonode
	byAssetPath = dict()    #kind of a pain, Houdini has no texture nodes.... key:asset path, value:mojonode

	def __init__( self, node, decl, decltype, args, argtypes, returntype, priority ):
		global uniqueIDCounter

		self.json = dict()
		self.node = node
		self.mojoID = None
		self.byHounode[node] = self

		uniqueIDCounter += 1
		self.uniqueID = "uniqueID<" + str(uniqueIDCounter) + ">"
		self.byReference[self.uniqueID] = self

		if not priority in self.byPriority.keys(): self.byPriority[priority] = []
		self.byPriority[priority].append( self )

		self.json["ctor"] ={"decl":decl,"args":args,"type": returntype+"("+listToString(argtypes)+")"}
		self.json["type"] = decltype
		self.json["state"] = dict()


class mojomesh:

	def __init__( self ):
		self.triangles = dict()		#keys: material name, value:triangles for each material
		self.materials = dict()		#keys: material name, value:dictionary with material attributes
		self.verts = []
		self.normals = []
		self.colors = []
		self.ids = []
		self.uv0 = []
		self.uv1 = []

	def getHouMesh( self, objnode ):
		normalStyle = 0
		colorStyle = 0
		hasUV = False
		global index
		
		# objnode = hou.node("..")
		# filename = hou.pwd().parm("filepath").eval()
		
		if objnode:
			#Check for valid object
			if not objnode.type().name() == "geo":
				hou.ui.displayMessage( "Output object must be of type geo" )
				return

			#Triangulate with temporary divide node
			div = objnode.createNode( "divide", "tempDivide" )
			div.setFirstInput( objnode.displayNode() )

			#Find UVs
			if div.geometry().findVertexAttrib("uv"):
				hasUV = True

			#Find color
			if div.geometry().findVertexAttrib("Cd"):
				colorStyle = 2
			elif div.geometry().findPointAttrib("Cd"):
				colorStyle = 1

			#Find normals
			if div.geometry().findVertexAttrib("N"):
				normalStyle = 2
			elif div.geometry().findPointAttrib("N"):
				normalStyle = 1

			#Prepare material groups and vertices
			mat = div.geometry().findPrimAttrib("shop_materialpath")

			triangles = dict()
			materials = dict()
			name = "default"

			#div has no materials per prim, we get the object material instead:
			objmatnode = hou.node( objnode.parm( "shop_materialpath").eval() )
			if objmatnode: name = self.getmaterial( objmatnode, materials )

			#Proceed getting data for each prim:
			for prim in div.geometry().prims():

				#Material/triangle group handling
				if mat:
					matnode = hou.node( prim.attribValue("shop_materialpath") )
					if matnode:
						name = self.getmaterial( matnode, materials )

				if not name in triangles.keys(): triangles[name] = []
				
				#Grab data from vertices!
				for v in prim.vertices():
					point = v.point().number()
					vert = vertex( point )

					vert.p = v.point().position()
					if hasUV: vert.uv0 = v.attribValue("uv")
					
					if normalStyle == 1:
						vert.n = v.point().attribValue("N")
					elif normalStyle == 2:
						vert.n = v.attribValue("N")

					if colorStyle == 1:
						vert.c = v.point().attribValue("Cd")
					elif colorStyle == 2:
						vert.c = v.attribValue("Cd")

					vert.mat = name

					#Optimization: Remove redundant vertices!
					#Here we determine if vert is unique or a match to an existing vertex
					match = vert
					if point in vertsByPoint.keys():
						for other in vertsByPoint[point]:
							if vert != other:
								if vert.n == other.n:
									if vert.uv0 == other.uv0:
										if vert.mat == other.mat:
											match = other
											break
						vertsByPoint[point].append(vert)
					else:
						vertsByPoint[point] = [vert]
					
					#Only write vertex data if is unique vertex
					if match == vert:	
						index += 1
						vert.index = index
						if vert.n:
							self.normals.append( vert.n[0] )
							self.normals.append( vert.n[1] )
							self.normals.append( vert.n[2] )

						if vert.c:
							self.colors.append( vert.c[0] )
							self.colors.append( vert.c[1] )
							self.colors.append( vert.c[2] )

						if vert.uv0:
							self.uv0.append( vert.uv0[0] )
							self.uv0.append( vert.uv0[1] )

						self.verts.append( vert.p.x() )
						self.verts.append( vert.p.y() )
						self.verts.append( vert.p.z() )
					
					#But always write triangle indices, per material
					if not name in self.triangles.keys(): self.triangles[name] = []
					self.triangles[name].append( match.index )

			self.materials = materials
					
			#Wrap it up
			div.destroy()
			# self.export( filename )
			mesh = None
			index = -1
			vertsByPoint.clear()

	def getmaterial( self, matnode, materials ):
		name = matnode.name()
		#Create material dictionary if not created yet
		if not name in materials.keys():
			materials[name] = dict()
			materials[name]["MetalnessFactor"] = matnode.parm( "metallic" ).eval()
			materials[name]["RoughnessFactor"] = matnode.parm( "rough" ).eval()
			materials[name]["ColorFactor"] = getcolor( matnode,"basecolor" )
			materials[name]["EmissiveFactor"] = getcolor( matnode,"emitcolor" )
			if matnode.parm( "basecolor_texture" ).eval(): materials[name]["ColorTexture"] = gettexture( matnode,"basecolor_texture" )
			if matnode.parm( "rough_texture" ).eval(): materials[name]["RoughnessTexture"] = gettexture( matnode,"rough_texture" )
			if matnode.parm( "metallic_texture" ).eval(): materials[name]["MetalnessTexture"] = gettexture( matnode,"metallic_texture" )
			if matnode.parm( "emitcolor_texture" ).eval(): materials[name]["EmissiveTexture"] = gettexture( matnode,"emitcolor_texture" )
			if matnode.parm( "baseNormal_texture" ).eval(): materials[name]["NormalTexture"] = gettexture( matnode,"baseNormal_texture" )
			print "Material: ",name,":\n",materials[name]
		return name

	def export( self, filename, exportMaterials = True ):
		jsondict = dict()
		jsondict["verts"] = self.verts
		jsondict["normals"] = self.normals
		jsondict["colors"] = self.colors
		jsondict["uv0"] = self.uv0
		jsondict["uv1"] = self.uv1
		jsondict["triangles"] = self.triangles
		if exportMaterials: jsondict["materials"] = self.materials

		json.encoder.FLOAT_REPR = lambda f: ("%.8f" % f)        #shortens float precision in json file to 8 decimals
		text = json.dumps( jsondict, sort_keys=True, indent=4, separators=(',',':') )
		text = compact( text )

		print "\nWriting mesh:\n",filename
		if not os.path.exists(os.path.dirname(filename)):
			try:
				os.makedirs(os.path.dirname(filename))
			except OSError as exc: # Guard against race condition
				if exc.errno != errno.EEXIST:
					raise

		textFile = open( filename, "w+" )
		textFile.write( text )
		textFile.close()

		print "Object stats:"
		print "verts:", len(self.verts)/3
		print "normals:", len(self.normals)/3
		print "uv0:", len(self.uv0)/2
		print "colors", len(self.colors)/3

		total = 0
		for t in self.triangles.values():
			total += (len(t)/3)

		print "triangles:", total
		print "triangle groups:", len(self.triangles)


class vertex:
	def __init__( self, point ):
		self.uv0 = []
		self.uv1 = []
		self.n = []
		self.p = []
		self.c = []
		self.mat = ""
		self.point = point


class flags:
	normal = 12
	cube = 516
	cubeMip = 524
	env = 1028
	envMip = 1036


#-------------------------------- Utilities ----------------------------------


def compact( t ):
	result = ""
	isArray = False
	for n in range(0, len(t)):
		char = t[n]
		if char == "[":
			isArray = True
		if char == "]":
			isArray = False
		if ( char == "\n" or char == " " ):
			if isArray:
				char = ""       
		if char == ",":
			char = ", "
		result += char
		previous = n
	result = result.replace( ", ", ",")
	return result


def listToString( l ):
	text = ""
	for s in l:
		text += s
		text += ","
	text = text[:-1]
	return text


def mojomatrix( n ):
	values = dict()
	values["translate"] = ( n.parm("tx").eval(), n.parm("ty").eval(), n.parm("tz").eval() * -1 )
	values["rotate"] = ( n.parm("rx").eval()*-1, n.parm("ry").eval() *-1, n.parm("rz").eval() )
	values["scale"] = ( n.parm("sx").eval(), n.parm("sy").eval(), n.parm("sz").eval() )

	xform = hou.hmath.buildTransform( values )
	localmtx = xform.asTuple()

	mojomtx = list()
	c = 1
	for e in localmtx:
		if c % 4 != 0:  #skip every fourth number
			mojomtx.append(e)
		c += 1
	return mojomtx


def isChild(n, parent):
	if len(n.inputs()) >= 1:
		i = n.inputs()[0]
		if i == parent:
			return True
		else:
			return isChild(i,parent)
	else:
		return False


def eval(n,p):
	return n.parm(p).eval()
	

def convertToAssetPath(originalPath):
	blocks = originalPath.split("/")
	last = len(blocks)-1
	pbr=""
	if blocks[last-1].endswith(".pbr"): pbr = blocks[last-1]+"/"
	return "asset::"+pbr+blocks[last]


#-------------------------------- Mojo Translators ----------------------------------


def buildtree( n, transformParent = None ):
	if n.type().name() == "matnet": return
	if not n.isDisplayFlagSet(): return
	getentity( n, transformParent )
	for o in n.outputs():
		buildtree( o )


def getentity( n, transformParent = None ):
	global path

	if n in mojonode.byHounode.keys(): return
	parent = getparent(n, transformParent)

	if n.type().name() == ("subnet"):
		entity = mojonode( n, "mojo3d.Pivot.New", "mojo3d.Pivot", [parent], ["mojo3d.Entity"], "Void", 4 )
		for c in n.children():
			inputs = c.inputs()
			if( not inputs ) or (n.inputs()[0] in inputs):
				buildtree( c, n )
	else:
		#detect reference to existing mojo model load
		mpath = getModelPath(n)
		modelpath = ""
		filemode = ""
		if mpath:
			modelpath = mpath[0]
			filemode = mpath[1]
		if modelpath:
			if modelpath in mojonode.byAssetPath.keys():
				#reference to file already exists, instance it
				model = mojonode.byAssetPath[modelpath]
				entity = mojonode( n, "mojo3d.Entity.Copy", "mojo3d.Entity", [parent], ["mojo3d.Entity"], "mojo3d.Entity", 5 )
				entity.json["ctor"]["inst"] = model.uniqueID
				if overrideMaterials: getAllMaterials(n)
			else:
				if filemode == "read" and not collapseHierachyOnLoad:
					entity = mojonode( n, "mojo3d.Model.LoadBoned", "mojo3d.Model", [modelpath], ["String"], "mojo3d.Model", 5 )
				else:
					entity = mojonode( n, "mojo3d.Model.Load", "mojo3d.Model", [modelpath], ["String"], "mojo3d.Model", 5 )
				mojonode.byAssetPath[modelpath] = entity
				mojonode.byHounode[n].json["state"]["Parent"] = parent
				if overrideMaterials: getAllMaterials(n)


		elif n.type().name().startswith("geo"):
			if n.children():
				mergeobj = getobjmerge(n)
				if mergeobj:
					#detect dependency loop
					if parent:
						if isChild(n,mergeobj):
							hou.ui.displayMessage( "Error: can't instance parent object. Will cause dependency loop!" )
							return
					entity = mojonode( n, "mojo3d.Entity.Copy", "mojo3d.Entity", [parent], ["mojo3d.Entity"], "mojo3d.Entity", 6 )
					entity.json["ctor"]["inst"] = mojonode.byHounode[mergeobj].uniqueID
					getAllMaterials(n)
				else:
					#This is not a subnet, loaded model or objmerge. Proceed with creating a model!
					prim = getprimitive(n)
					if prim:
						#there's a mesh!
						args = [prim,getmaterial(n),parent]
						argtypes = ["mojo3d.Mesh","mojo3d.Material","mojo3d.Entity"]
						entity = mojonode( n, "mojo3d.Model.New", "mojo3d.Model", args, argtypes, "Void", 4 )
						color = getcolornode(n)
						if color: mojonode.byHounode[n].json["state"]["Color"] = color
					else:
						#If we get here, it means the mesh is not a primitive (platonic) object. This is a custom model.
						#Let's save it in mojomesh (.json) format.
						folder = path.split("/")
						meshpath = "/".join( folder[ 0: len(folder)-1 ] ) + "/meshes/" + n.name() + ".json"

						meshData = mojomesh()
						meshData.getHouMesh( n )
						meshData.export( meshpath )

						args = [ "asset::" + n.name() + ".json" ]
						argtypes = ["String"]
						entity = mojonode( n, "mojogame.LoadJsonModel", "mojo3d.Model", args, argtypes, "mojo3d.Model", 3 )
			else:
				args = [parent]
				argtypes = ["mojo3d.Entity"]
				entity = mojonode( n, "mojo3d.Pivot.New", "mojo3d.Pivot", args, argtypes, "Void", 4 )

		elif n.type().name().startswith("hlight"):
			if not n.parm("light_enable").eval(): return
			if not n.parm("ogl_enablelight").eval(): return

			args = [parent]
			argtypes = ["mojo3d.Entity"]
			entity = mojonode( n, "mojo3d.Light.New", "mojo3d.Light", args, argtypes, "Void", 4 )
			mojolight = 1
			if n.parm("light_type").eval() == 0: mojolight = 2
			if n.parm("coneenable").eval() == 1: mojolight = 3
			if n.parm("light_type").eval() >= 7: mojolight = 1
			mojoshadow = 0
			if n.parm("shadow_type").eval() > 0: mojoshadow = 1
			atten_type = n.parm("atten_type").eval()
			mojorange = 100.0
			if atten_type == 0: mojorange = 100000.0                                                #virtually no attentuation
			elif atten_type == 1: mojorange = n.parm("atten_dist").eval() * 25.0                    #not correct at all...
			else: hou.ui.displayMessage( "Export Warning: unsupported light attentuation type" )    #inverse square, not implemented in mojo yet?

			mojonode.byHounode[n].json["state"]["Color"] = getcolor(n,"light_color",1.0,n.parm("light_intensity").eval())
			mojonode.byHounode[n].json["state"]["Type"] = mojolight
			mojonode.byHounode[n].json["state"]["CastsShadow"] = mojoshadow
			mojonode.byHounode[n].json["state"]["Range"] = mojorange
			mojonode.byHounode[n].json["state"]["OuterAngle"] = (n.parm("coneangle").eval()/2.0) + n.parm("conedelta").eval()
			mojonode.byHounode[n].json["state"]["InnerAngle"] = n.parm("coneangle").eval()/2.0

		elif n.type().name().startswith("cam"):
			args = [parent]
			argtypes = ["mojo3d.Entity"]
			entity = mojonode( n, "mojo3d.Camera.New", "mojo3d.Camera", args, argtypes, "Void", 4 )
			mojonode.byHounode[n].json["state"]["Near"] = n.parm("near").eval()
			mojonode.byHounode[n].json["state"]["Far"] = n.parm("far").eval()
			mojonode.byHounode[n].json["state"]["FOV"] = 2.0 * math.degrees( math.atan ( ( ( (n.parm("resy").eval()*n.parm("aperture").eval() ) / (n.parm("resx").eval() ) )/2.0) / n.parm("focal").eval() ) )

		elif n.type().name().startswith("envlight"):
			mojonode.byHounode[root].json["state"]["EnvColor"] = getcolor(n, "light_color", 1.0 )
			mojonode.byHounode[root].json["state"]["EnvTexture"] = gettexture(n, "env_map", flags.envMip )
			mojonode.byHounode[root].json["state"]["SkyTexture"] = gettexture(n, "env_map", flags.envMip )
			return
		
		elif n.type().name().startswith("ambient"):
			mojonode.byHounode[root].json["state"]["AmbientLight"] = getcolor(n, "light_color", 1.0, 1.0)
			return
		else:
			print "Not a valid Mojo3D node:", n.type().name(), n.name()
			return

	#Basic Entity states
	mojonode.byHounode[n].json["state"]["Name"] = n.name()
	mojonode.byHounode[n].json["state"]["LocalMatrix"] = mojomatrix( n )

	
def getparent(n, transformParent=None):
	if transformParent:
		parent = mojonode.byHounode[transformParent]
		return parent.uniqueID
	if len(n.inputs()) == 1:
		print n
		pnode = n.inputs()[0]
		if not pnode in mojonode.byHounode.keys(): getentity(pnode)
		parent = mojonode.byHounode[pnode]
		return parent.uniqueID
	else:
		return None


def getcolor(n,pname,alpha = 1.0, multiplier = 1.0):
	return [math.pow(n.parm(pname+"r").eval()*multiplier, 1/2.2),
		math.pow(n.parm(pname+"g").eval()*multiplier, 1/2.2),
		math.pow(n.parm(pname+"b").eval()*multiplier, 1/2.2),
		alpha ]


def getcolornode(n):
	for c in n.children():
		if c.type().name() == "matnet": return None
		if c.isBypassed(): return None
		if c.type().name() == "color":
			return getcolor(c,"color")
	return None


def getobjmerge(n):
	for c in n.children():
		if c.type().name() == "matnet": return None
		if c.isBypassed(): return None
		if c.type().name() == "object_merge":
			objpath = c.parm("objpath1").eval()
			if objpath:
				hounode = hou.node( objpath )
				if not hounode in mojonode.byHounode.keys(): getentity(hounode)
				return hounode

	return None


def getbox(n,pname):
	x=n.parm(pname+"x").eval()
	y=n.parm(pname+"y").eval()
	z=n.parm(pname+"z").eval()
	tx=n.parm("tx").eval()
	ty=n.parm("ty").eval()
	tz=n.parm("tz").eval()
	return [ (-x/2.0)+tx,(-y/2.0)+ty, (-z/2.0)+tz, (x/2.0)+tx, (y/2.0)+ty, (z/2.0)+tz ]
	

def getmaterial(n):
	if n.parm( "shop_materialpath"):
		matpath = n.parm( "shop_materialpath").eval()
		matnode = hou.node( matpath )
		if matnode:
			#Build material node, if doesn't exist already
			if not matnode in mojonode.byHounode.keys():
				args = [ getcolor(matnode,"basecolor",1.0), matnode.parm("metallic").eval(), matnode.parm("rough").eval() ]
				argtypes = ["std.graphics.Color","Float","Float"]
				mat = mojonode( matnode, "mojo3d.PbrMaterial.New", "mojo3d.PbrMaterial", args, argtypes, "Void", 2 )
				getMaterialState(mat)
				return mat.uniqueID
			else:
				return mojonode.byHounode[ matnode ].uniqueID
		else:
			# hou.ui.displayMessage( "Mojo Exporter Warning: Entity " + n.name() + " has no material!")
			if "DefaultMaterial" in mojonode.byAssetPath.keys():
				return mojonode.byAssetPath["DefaultMaterial"].uniqueID
			else:
				args = [ [0.7, 0.7, 0.7, 1.0], 0.0, 0.5 ]
				argtypes = ["std.graphics.Color","Float","Float"]
				mat = mojonode( None, "mojo3d.PbrMaterial.New", "mojo3d.PbrMaterial", args, argtypes, "Void", 2 )
				mojonode.byAssetPath["DefaultMaterial"] = mat
				return mat.uniqueID
			# return None


def getMaterialState(matnode):
	if eval(matnode.node,"basecolor_texture"):matnode.json["state"]["ColorTexture"] = gettexture(matnode.node,"basecolor_texture")
	if eval(matnode.node,"rough_texture"):matnode.json["state"]["RoughnessTexture"] = gettexture(matnode.node,"rough_texture")
	if eval(matnode.node,"metallic_texture"):matnode.json["state"]["MetalnessTexture"] = gettexture(matnode.node,"metallic_texture")
	if eval(matnode.node,"emitcolor_texture"):matnode.json["state"]["EmissiveTexture"] = gettexture(matnode.node,"emitcolor_texture")
	if eval(matnode.node,"baseNormal_texture"):matnode.json["state"]["NormalTexture"] = gettexture(matnode.node,"baseNormal_texture")


def getAllMaterials(n):
	matpaths = []
	matnodes = []
	mat_ids = []

	if n.parm( "shop_materialpath"): matpaths.append( n.parm( "shop_materialpath").eval() )

	for c in n.children():
		if c.type().name() == "material":
			if c.isBypassed(): continue
			matpaths.append( c.parm("shop_materialpath1").eval() )

	for m in matpaths:
		if m != "": matnodes.append( hou.node( m ) )

	for matnode in matnodes:
		#Build material node, if doesn't exist already
		if not matnode in mojonode.byHounode.keys():
			args = [ getcolor(matnode,"basecolor",1.0), matnode.parm("metallic").eval(), matnode.parm("rough").eval() ]
			argtypes = ["std.graphics.Color","Float","Float"]
			mat = mojonode( matnode, "mojo3d.PbrMaterial.New", "mojo3d.PbrMaterial", args, argtypes, "Void", 2 )
			getMaterialState(mat)
			mat_ids.append( mat.uniqueID )
		else:
			mat_ids.append( mojonode.byHounode[ matnode ].uniqueID )

	if mat_ids: mojonode.byHounode[n].json["state"]["Materials"] = mat_ids
		

def getprimitive(n):
	displayNode = None
	displayPointCount = 0

	for c in n.children():
		if c.isBypassed(): return None
		if c.isGenericFlagSet( hou.nodeFlag.Display ): displayPointCount = len(c.geometry().points())

		name = c.type().name()
		if name == "grid":
			if len(c.geometry().points()) != displayPointCount: return None
			width = c.parm("sizex").eval()
			height = c.parm("sizey").eval()
			args = [ [-width/2.0, -height/2.0, width/2.0, height/2.0] ]
			argtypes = ["std.geom.Rect<monkey.types.Float>"]
			mesh = mojonode( c, "mojo3d.Mesh.CreateRect", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
			return mesh.uniqueID
		elif name == "torus":
			if len(c.geometry().points()) != displayPointCount: return None
			args = [ c.parm("radx").eval(), c.parm("rady").eval(), c.parm("cols").eval(), c.parm("rows").eval() ]
			argtypes = ["Float","Float","Int","Int"]
			mesh = mojonode( c, "mojo3d.Mesh.CreateTorus", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
			return mesh.uniqueID
		elif name == "sphere":
			if len(c.geometry().points()) != displayPointCount: return None
			args = [ c.parm("radx").eval() * c.parm("scale").eval(), c.parm("rows").eval(), c.parm("cols").eval() ]
			argtypes = ["Float","Int","Int"]
			mesh = mojonode( c, "mojo3d.Mesh.CreateSphere", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
			return mesh.uniqueID
		elif name == "box":
			if len(c.geometry().points()) != displayPointCount: return None
			args = [ getbox(c,"size"),1,1,1 ]
			argtypes = ["std.geom.Box<monkey.types.Float>","Int","Int","Int"]
			mesh = mojonode( c, "mojo3d.Mesh.CreateBox", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
			return mesh.uniqueID
		elif name == "tube":
			if len(c.geometry().points()) != displayPointCount: return None
			if c.parm("rad1").eval() == 0:
				args = [ c.parm("rad2").eval(), c.parm("height").eval(), c.parm("orient").eval(), c.parm("cols").eval() ]
				argtypes = ["Float", "Float", "std.geom.Axis","Int"]
				mesh = mojonode( c, "mojo3d.Mesh.CreateCone", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
				return mesh.uniqueID
			else:
				args = [ c.parm("rad2").eval(), c.parm("height").eval(), c.parm("orient").eval(), c.parm("cols").eval() ]
				argtypes = ["Float", "Float", "std.geom.Axis","Int"]
				mesh = mojonode( c, "mojo3d.Mesh.CreateCylinder", "mojo3d.Mesh", args, argtypes, "mojo3d.Mesh", 3 )
				return mesh.uniqueID
	return None


def gettexture(n,pname, flags=12):
	texpath = n.parm(pname).eval()
	if not texpath in mojonode.byAssetPath.keys():
		if convertToAssetPaths:
			texpath=convertToAssetPath(texpath)
		args = [ texpath, flags, False ]
		argtypes = ["String", "mojo.graphics.TextureFlags", "Bool" ]
		texture = mojonode( None, "mojo3d.Scene.LoadTexture", "mojo.graphics.Texture", args, argtypes, "mojo.graphics.Texture", 1 )
		texture.json["ctor"]["inst"] = "@0"
		mojonode.byAssetPath[texpath] = texture
		return texture.uniqueID
	else:
		return mojonode.byAssetPath[texpath].uniqueID


def getcomponents():
	pass


def getModelPath(n, depth=0):
	modelpath = ""
	filemode = ""
	#exception for cameras and lights, which contain a file node
	if n.type().name().startswith("cam") or n.type().name().startswith("hlight") or n.type().name().startswith("ambient"):
		return None

	#search fbx output nodes
	for f in hou.node("/out").children():
		if f.type().name() == "filmboxfbx":
			if f.parm("startnode").eval() == n.path():
				file = f.parm("sopoutput").eval()
				filemode = "write"
				if convertSaversToGlb: file = file.replace(".fbx", ".glb")
				if convertToAssetPaths: file = convertToAssetPath(file)
				print file
				return file, filemode

	#search for file nodes
	for c in n.children():
		if c.type().name() == "file":
			modelpath = c.parm("file").eval().split("#")[0]
			if modelpath:
				if c.parm("filemode").eval() == 2:     #file mode is "write"
					filemode = "write"
					if convertSaversToGlb:
						modelpath = modelpath.replace(".fbx", ".glb")
						modelpath = modelpath.replace(".obj", ".glb")
				else:
					filemode = "read"
					if convertLoadersToGlb:
						modelpath = modelpath.replace(".fbx", ".glb")
						modelpath = modelpath.replace(".obj", ".glb")

				if convertToAssetPaths:
					modelpath = convertToAssetPath(modelpath)
				break
		elif c.type().name() == "rop_fbx":
			modelpath = c.parm("sopoutput").eval()
			if modelpath:
				filemode = "read"
				if convertLoadersToGlb: modelpath = modelpath.replace(".fbx", ".glb")
				if convertToAssetPaths: modelpath = convertToAssetPath(modelpath)
				break
		else:
			result = getModelPath(c,depth+1)
			if result:
				modelpath = result[0]
				filemode = result[1]
	return modelpath, filemode


#-------------------------------- Exporter ----------------------------------


def export():
	global convertLoadersToGlb
	global convertSaversToGlb
	global convertToAssetPaths
	global collapseHierachyOnLoad
	global overrideMaterials
	global path

	# path = hou.pwd().parm("path").eval()
	path = hou.ui.selectFile( "$JOB", "Choose file to export to" )

	choices = hou.ui.selectFromList(
		("Convert Savers to .glb",
		"Convert Loaders to .glb ",
		"Convert paths to asset paths",
		"Collapse Hierarchy on Load",
		"Override Model Materials" ),
		(2,4) )

	if 0 in choices: convertSaversToGlb=True
	if 1 in choices: convertLoadersToGlb=True
	if 2 in choices: convertToAssetPaths=True
	if 3 in choices: collapseHierachyOnLoad=True
	if 4 in choices: overrideMaterials=True

	# convertSaversToGlb=False
	# convertLoadersToGlb=False
	# convertToAssetPaths=True
	# collapseHierachyOnLoad=False
	# overrideMaterials=True

	# clear shell
	print "\n" * 5000
	print "\nExporting Scene to Json file:\n", path
	print "---------------------------------------------------------------------------------------------------"

	#Create scene node with default state
	scene = mojonode( root, "mojo3d.Scene.New", "mojo3d.Scene", [True], ["Bool"], "Void", 0 )
	scene.json["state"]["EnvColor"] = [0,0,0,1]
	scene.json["state"]["EnvTexture"] = None
	scene.json["state"]["SkyTexture"] = None
	scene.json["state"]["AmbientLight"] = [0,0,0,1]
	scene.json["state"]["ClearColor"] = [0,0,0,1]

	#find entities, set priorities
	for c in root.children():
		inputs = c.inputs()
		if not inputs:
			buildtree( c )

	#Assigns mojo id to each node and builds ordered node list
	index = 0
	for level in mojonode.byPriority.keys():
		for n in mojonode.byPriority[ level ]:
			n.mojoID = "@" + str(index)
			n.json["id"] = n.mojoID
			orderedNodes.append( n )
			index += 1

	#Add instances to root json dictionary
	jsondict["instances"] = []
	for n in orderedNodes:
		if "state" in n.json.keys():
			if not n.json["state"]: n.json.pop("state")
		jsondict["instances"].append( n.json )

	#Json to text
	text = json.dumps( jsondict, sort_keys=True, indent=4, separators=(',',':') )
	text = compact( text )

	#Convert references to paths to instance ids
	for r in mojonode.byReference.keys():
		n = mojonode.byReference[r]
		text = text.replace( r, n.mojoID )

	#Finish up
	# print text
	textFile = open( path, "w+" )
	textFile.write( text )
	textFile.close()
	print "\nExport finished!\n"
	
	print "total mojonodes:",len(orderedNodes)
	print "mojonode priorities:",len(mojonode.byPriority)
	print "Objects by priority:"
	for l in mojonode.byPriority.values():
		for n in l:
			if n:
				if n.node:
					print n.node.name(), n.mojoID
				else:
					print n.uniqueID, n.mojoID

	print "\n----------------------------------------------------------------------------------------------------"