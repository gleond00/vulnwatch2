/* SITIOS CONFIG */

LOCK TABLES `gestion_app_sitio` WRITE;
INSERT INTO `gestion_app_sitio` VALUES
(1,1,'Sala de Espera','Sala de espera del hospital',0,5,1,NULL),
(2,4,'Box 1','Box para tratar pacientes',0,8,NULL,NULL),
(3,5,'Box 2','Descripcion',0,0,NULL,NULL),
(4,2,'Triaje','Habitación empleada para triaje dentro de urgencias.',0,0,NULL,NULL),
(5,3,'Sala de Información','Sala de urgencias para que los pacientes reciban informacion',0,0,NULL,NULL),
(6,6,'Box 3','Descripcion',0,0,NULL,NULL),
(7,7,'Box 4','Descripcion',0,0,NULL,NULL),
(8,8,'Box 5','Descripcion',0,0,NULL,NULL),
(9,9,'Box 6','Descripcion',0,0,NULL,NULL),
(10,10,'Box 7','Descripcion',0,0,NULL,NULL),
(11,11,'Box 8','Descripcion',0,0,NULL,NULL),
(12,12,'Box 9','Descripcion',0,0,NULL,NULL),
(13,13,'Box 10','Descripcion',0,0,NULL,NULL),
(14,14,'Observación','Sala en la que los pacientes permanecen en observación',0,0,NULL,NULL),
(15,15,'Pendiente de Ambulancia','Sala en la que los pacientes esperan a que llegue la ambulancia',0,0,NULL,NULL),
(16,16,'Planta','Sala de panta en la que se situan los paciente',0,0,NULL,NULL),
(17,17,'Alta','Sitio que sirve para ver los pacientes que ya han sido dados de alta',0,0,NULL,NULL);
UNLOCK TABLES;

LOCK TABLES `gestion_app_estado` WRITE;
INSERT INTO `gestion_app_estado` VALUES
(1,1,'Espere','',1,1),
(3,1,'Paciente Pase','',NULL,2),
(5,2,'Acompañante Pase','',NULL,2),
(6,2,'Acompañante Pase','',NULL,3),
(7,1,'Familiar Espere','',NULL,3),
(9,1,'Paciente Pase','Indica a paciente que puede pasar a la sala',NULL,4),
(10,2,'Acompañante Pase','Indica al acompañante del paciente que puede pasar a la sala',NULL,4),
(11,1,'Pase','',NULL,5),
(12,1,'Familiar Espere','',NULL,6),
(13,2,'Acompañante Pase','',NULL,6),
(14,1,'Familiar Espere','',NULL,7),
(15,2,'Acompañante Pase','',NULL,7),
(16,1,'Familiar Espere','',NULL,8),
(17,2,'Acompañante Pase','',NULL,8),
(18,1,'Familiar Espere','',NULL,9),
(19,2,'Acompañante Pase','',NULL,9),
(20,1,'Familiar Espere','',NULL,10),
(21,2,'Acompañante Pase','',NULL,10),
(22,1,'Familiar Espere','',NULL,11),
(23,2,'Acompañante Pase','',NULL,11),
(24,1,'Familiar Espere','',NULL,12),
(25,2,'Acompañante Pase','',NULL,12),
(26,1,'Familiar Espere','',NULL,13),
(27,2,'Acompañante Pase','',NULL,13),
(28,1,'En espera','',NULL,14),
(29,2,'Acompañante pase','',NULL,14),
(30,1,'En espera','',NULL,15),
(31,1,'Espere','',NULL,16),
(32,1,'Dado de alta','',NULL,17);
UNLOCK TABLES;

LOCK TABLES `gestion_app_sitio_sitios_visibles` WRITE;
INSERT INTO `gestion_app_sitio_sitios_visibles` VALUES
(1,1,1),
(15,1,2),
(16,1,3),
(17,1,4),
(18,1,6),
(19,1,7),
(20,1,8),
(21,1,9),
(22,1,10),
(23,1,11),
(24,1,12),
(25,1,13),
(40,1,14),
(41,1,15),
(38,1,16),
(39,1,17),
(2,2,2),
(4,3,3),
(13,4,4),
(14,5,5),
(26,6,6),
(27,7,7),
(28,8,8),
(29,9,9),
(30,10,10),
(31,11,11),
(32,12,12),
(33,13,13),
(34,14,14),
(35,15,15),
(36,16,16),
(37,17,17);
UNLOCK TABLES;


/* PERFIL CONFIG */

LOCK TABLES `gestion_app_perfil` WRITE;
INSERT INTO `gestion_app_perfil` VALUES
(1,1,1,1);
UNLOCK TABLES;

LOCK TABLES `gestion_app_perfil_destinos_permitidos` WRITE;
INSERT INTO `gestion_app_perfil_destinos_permitidos` VALUES
(1,1,1),
(3,1,2),
(5,1,3),
(6,1,4),
(7,1,5),
(8,1,6),
(9,1,7),
(10,1,8),
(11,1,9),
(12,1,10),
(13,1,11),
(14,1,12),
(15,1,13),
(16,1,14),
(17,1,15),
(18,1,16),
(19,1,17);
UNLOCK TABLES;

LOCK TABLES `gestion_app_asignacionmodo` WRITE;
INSERT INTO `gestion_app_asignacionmodo` VALUES
(1,2,1,1,1),
(3,2,1,1,2),
(4,2,1,1,3),
(5,0,1,1,6),
(6,0,1,1,7),
(7,0,1,1,8),
(8,0,1,1,9),
(9,0,1,1,10),
(10,0,1,1,11),
(11,0,1,1,12),
(12,0,1,1,13),
(13,0,1,1,14),
(14,0,1,1,15),
(15,0,1,1,16),
(16,0,1,1,17),
(19,2,1,1,4);
UNLOCK TABLES;

LOCK TABLES `config_app_acreditacion` WRITE;
INSERT INTO `config_app_acreditacion` VALUES
(1,NULL,'Acreditacion de prueba','Api_tokenn',1);
UNLOCK TABLES;


/*HL7 CONFIG*/