using System.Text.Json;
using System.Text;
using System.Xml.Serialization;
using System.Xml.Linq;
using CsvHelper;
using CsvHelper.Configuration;
using System.Globalization;
using System.Dynamic;
using static System.Net.Mime.MediaTypeNames;
using System.ComponentModel.DataAnnotations;

namespace Program
{
	public class DPDCsv
	{
		private string _type = "";

		public string TypeEnvoi
		{
			get { return _type; }
			set
			{
				if (
					value == "Predict"
					|| value == "No"
					|| value == "AutomaticSMS"
					|| value == "AutomaticMail"
					|| value == ""
					)
					_type = value;
				else
					throw new ArgumentException("La valeur doit être 'Predict' ou 'No' ou 'AutomaticSMS' ou 'AutomaticMail' (ou '' quand l'envoi est un MultiShipment)");
			}
		}

		public string Reference { get; set; } = "";
		public string Poids { get; set; } = "";


		//

		public string NomEmmetteur { get; set; } = "";
		public string EmailEmmetteur { get; set; } = "";
		public string TelephoneEmmetteur { get; set; } = "";
		public string PrefixPaysEmmetteur { get; set; } = "";
		public string RueEmmetteur { get; set; } = "";
		public string CodePostalEmmetteur { get; set; } = "";
		public string VilleEmmetteur { get; set; } = "";

		//
		// à implémenter
		//public string Remarque { get; set; } = "";
		//

		public string NomRecepteur { get; set; } = "";
		public string EmailRecepteur { get; set; } = "";
		public string TelephoneRecepteur { get; set; } = "";
		public string PrefixPaysRecepteur { get; set; } = "";
		public string RueRecepteur { get; set; } = "";
		public string RueRecepteur2 { get; set; } = "";
		public string RueRecepteur3 { get; set; } = "";
		public string RueRecepteur4 { get; set; } = "";
		public string CodePostalRecepteur { get; set; } = "";
		public string VilleRecepteur { get; set; } = "";

		//

		public int NumeroCentreClient { get; set; } = 0;
		public int NumeroClient { get; set; } = 0;
		public int NumeroColis { get; set; } = 1;
		public int NombreTotalColis { get; set; } = 1;

	}



	public class Program
	{
		public async static Task program(string[] args)
		{




			if (args.Length != 1)
			{
				Console.WriteLine("Utilisation du programme: dpd_to_png.exe \"C:\\chemin\\vers\\le\\fichier\"");
				return;
			}

			string filePath = args[0];

			if (!File.Exists(filePath))
			{
				Console.WriteLine("Le fichier '{0}' n'existe pas.", filePath);
				return;
			}






			// bic3data mode	: OnlyStdLabels or OnlyBic3 or All
			// contact type		: No or Predict or AutomaticSMS or AutomaticMail
			string template_simpleshipment = @"<?xml version=""1.0"" encoding=""utf-8""?>
<soap:Envelope xmlns:xsi=""http://www.w3.org/2001/XMLSchema-instance"" xmlns:xsd=""http://www.w3.org/2001/XMLSchema"" xmlns:soap=""http://schemas.xmlsoap.org/soap/envelope/"">
	<soap:Header>
		<UserCredentials xmlns=""http://www.cargonet.software"">
			<userid><REDACTED></userid>
			<password><REDACTED></password>
		</UserCredentials>
	</soap:Header>
	<soap:Body>
		<CreateShipmentWithLabelsBc xmlns=""http://www.cargonet.software"">
			<request>
				<bic3data>
					<mode>All</mode>
				</bic3data>
				<contact>
					<sms>$TelephoneRecepteur</sms>
					<email>$EmailRecepteur</email>
					<type>$TypeEnvoi</type>
					<autoText></autoText>
				</contact>
				<customer_countrycode>250</customer_countrycode>
				<customer_centernumber>$NumeroCentreClient</customer_centernumber>
				<customer_number>$NumeroClient</customer_number>
				<shipperaddress>
					<countryPrefix>$PrefixPaysEmmetteur</countryPrefix>
					<city>$VilleEmmetteur</city>
					<zipCode>$CodePostalEmmetteur</zipCode>
					<street>$RueEmmetteur</street>
					<name>$NomEmmetteur</name>
					<phoneNumber>$TelephoneEmmetteur</phoneNumber>
				</shipperaddress>
				<receiveraddress>
					<countryPrefix>$PrefixPaysRecepteur</countryPrefix>
					<city>$VilleRecepteur</city>
					<zipCode>$CodePostalRecepteur</zipCode>
					<street>$RueRecepteur</street>
					<name>$NomRecepteur</name>
					<phoneNumber>$TelephoneRecepteur</phoneNumber>
				</receiveraddress>
				<receiverinfo>
					<name2>$RueRecepteur2</name2>
					<name3>$RueRecepteur3</name3>
					<name4>$RueRecepteur4</name4>
				</receiverinfo>
				<refnrasbarcode>true</refnrasbarcode>
				<referencenumber>$Reference</referencenumber>
				<referenceInBarcode>
					<type>Referencenumber</type>
				</referenceInBarcode>
				<weight>$Poids</weight>
			</request>
		</CreateShipmentWithLabelsBc>
	</soap:Body>
</soap:Envelope>
";

			string template_multishipment = @"<?xml version=""1.0"" encoding=""utf-8""?>
<soap12:Envelope xmlns:xsi=""http://www.w3.org/2001/XMLSchema-instance"" xmlns:xsd=""http://www.w3.org/2001/XMLSchema"" xmlns:soap12=""http://www.w3.org/2003/05/soap-envelope"">
	<soap12:Header>
		<UserCredentials xmlns=""http://www.cargonet.software"">
			<userid><REDACTED></userid>
			<password><REDACTED></password>
		</UserCredentials>
	</soap12:Header>
	<soap12:Body>
		<CreateMultiShipmentBc xmlns=""http://www.cargonet.software"">
			<request>
				<customer_countrycode>250</customer_countrycode>
				<customer_centernumber>$NumeroCentreClient</customer_centernumber>
				<customer_number>$NumeroClient</customer_number>
				<shipperaddress>
					<countryPrefix>$PrefixPaysEmmetteur</countryPrefix>
					<city>$VilleEmmetteur</city>
					<zipCode>$CodePostalEmmetteur</zipCode>
					<street>$RueEmmetteur</street>
					<name>$NomEmmetteur</name>
					<phoneNumber>$TelephoneEmmetteur</phoneNumber>
				</shipperaddress>
				<receiveraddress>
					<countryPrefix>$PrefixPaysRecepteur</countryPrefix>
					<city>$VilleRecepteur</city>
					<zipCode>$CodePostalRecepteur</zipCode>
					<street>$RueRecepteur</street>
					<name>$NomRecepteur</name>
					<phoneNumber>$TelephoneRecepteur</phoneNumber>
				</receiveraddress>
				<receiverinfo>
					<name2>$RueRecepteur2</name2>
					<name3>$RueRecepteur3</name3>
					<name4>$RueRecepteur4</name4>
				</receiverinfo>
				<dayCheckDone>true</dayCheckDone>
				<pick_date>$date</pick_date>
				<time_from>08:00</time_from>
				<time_to>18:00</time_to>
				<services>
					<consolidation>
						<type>CombinedDelivery</type>
					</consolidation>
					<contact>
						<type>No</type>
					</contact>
				</services>
				<slaves>
					$slaverequest
				</slaves>
			</request>
		</CreateMultiShipmentBc>
	</soap12:Body>
</soap12:Envelope>";

			var template_getlabel = @"<?xml version=""1.0"" encoding=""utf-8""?>
<soap:Envelope xmlns:xsi=""http://www.w3.org/2001/XMLSchema-instance"" xmlns:xsd=""http://www.w3.org/2001/XMLSchema"" xmlns:soap=""http://schemas.xmlsoap.org/soap/envelope/"">
	<soap:Header>
		<UserCredentials xmlns=""http://www.cargonet.software"">
			<userid><REDACTED></userid>
			<password><REDACTED></password>
		</UserCredentials>
	</soap:Header>
	<soap:Body>
		<GetLabelBc xmlns=""http://www.cargonet.software"">
			<request>
				<shipmentNumber>$shipmentnumber</shipmentNumber>
				<customer_countrycode>250</customer_countrycode>
				<customer_centernumber>$NumeroCentreClient</customer_centernumber>
				<customer_number>$NumeroClient</customer_number>
			</request>
		</GetLabelBc>
	</soap:Body>
</soap:Envelope>";

			var template_slaverequest = @"<SlaveRequest>
	<weight>$Poids</weight>
	<referencenumber>$referencenumber</referencenumber>
	<services xsi:nil=""true"" />
	</SlaveRequest>";

			using var reader = new StreamReader(filePath);
			using var csv = new CsvReader(reader, new CsvConfiguration(CultureInfo.InvariantCulture) { Delimiter = ";" });
			var records = csv.GetRecords<DPDCsv>();
			HttpClient sharedClient = new();
			var slaverequest = "";


			foreach (var record in records)
			{
				if (record.NombreTotalColis == 1) // shimple shipment
				{

					sharedClient.DefaultRequestHeaders.Remove("SOAPAction");
					sharedClient.DefaultRequestHeaders.Add("SOAPAction", "http://www.cargonet.software/CreateShipmentWithLabelsBc");

					string xmlrequest = template_simpleshipment
						.Replace("$EmailRecepteur", record.EmailRecepteur)
						.Replace("$PrefixPaysRecepteur", record.PrefixPaysRecepteur)
						.Replace("$VilleRecepteur", record.VilleRecepteur)
						.Replace("$CodePostalRecepteur", record.CodePostalRecepteur)
						.Replace("$RueRecepteur2", record.RueRecepteur2)
						.Replace("$RueRecepteur3", record.RueRecepteur3)
						.Replace("$RueRecepteur4", record.RueRecepteur4)
						.Replace("$RueRecepteur", record.RueRecepteur)
						.Replace("$NomRecepteur", record.NomRecepteur)
						.Replace("$TelephoneRecepteur", record.TelephoneRecepteur)

						.Replace("$EmailEmmetteur", record.EmailEmmetteur)
						.Replace("$PrefixPaysEmmetteur", record.PrefixPaysEmmetteur)
						.Replace("$VilleEmmetteur", record.VilleEmmetteur)
						.Replace("$CodePostalEmmetteur", record.CodePostalEmmetteur)
						.Replace("$RueEmmetteur", record.RueEmmetteur)
						.Replace("$NomEmmetteur", record.NomEmmetteur)
						.Replace("$TelephoneEmmetteur", record.TelephoneEmmetteur)

						.Replace("$TypeEnvoi", record.TypeEnvoi)
						.Replace("$Poids", record.Poids)
						.Replace("$Reference", record.Reference)
						.Replace("$NumeroCentreClient", record.NumeroCentreClient.ToString())
						.Replace("$NumeroClient", record.NumeroClient.ToString());


					//Console.WriteLine("Requête : \n{0}\n", xml2);

					// Create the HTTP request content
					StringContent requestContent = new(xmlrequest, Encoding.UTF8, "text/xml");

					// Send the POST request
					using HttpResponseMessage response = await sharedClient.PostAsync("https://e-station-testenv.cargonet.software/eprintwebservice/eprintwebservice.asmx", requestContent);

					// Check the response status and read the content
					if (response.IsSuccessStatusCode)
					{
						string responseContent = await response.Content.ReadAsStringAsync();
						XNamespace ns = "http://www.cargonet.software";
						XElement image = XDocument.Parse(responseContent).Descendants(ns + "label").First();
						byte[] imageBytes = Convert.FromBase64String(image.Value);
						string file = string.Format("{0}\\{1}.png", Path.GetDirectoryName(filePath), record.Reference);
						File.WriteAllBytes(file, imageBytes);
						//Console.WriteLine(file);
					}
					else
					{
						Console.Error.WriteLine("something went wrong 1");
						Console.WriteLine($"Error: {response.StatusCode} - {response.ReasonPhrase}");
						string responseContent = await response.Content.ReadAsStringAsync();
						Console.WriteLine(XDocument.Parse(responseContent).ToString());
					}
				}
				else if (record.NombreTotalColis != 1 & record.NumeroColis != record.NombreTotalColis)
				{
					slaverequest += template_slaverequest
						.Replace("$Poids", record.Poids)
						.Replace("$referencenumber", record.Reference)
						+ "\n";
				}
				else if (record.NumeroColis == record.NombreTotalColis)
				{
					slaverequest += template_slaverequest
						.Replace("$Poids", record.Poids)
						.Replace("$referencenumber", record.Reference);

					string xmlrequest = template_multishipment
						.Replace("$PrefixPaysRecepteur", record.PrefixPaysRecepteur)
						.Replace("$VilleRecepteur", record.VilleRecepteur)
						.Replace("$CodePostalRecepteur", record.CodePostalRecepteur)
						.Replace("$RueRecepteur2", record.RueRecepteur2)
						.Replace("$RueRecepteur3", record.RueRecepteur3)
						.Replace("$RueRecepteur4", record.RueRecepteur4)
						.Replace("$RueRecepteur", record.RueRecepteur)
						.Replace("$NomRecepteur", record.NomRecepteur)
						.Replace("$TelephoneRecepteur", record.TelephoneRecepteur)

						.Replace("$PrefixPaysEmmetteur", record.PrefixPaysEmmetteur)
						.Replace("$VilleEmmetteur", record.VilleEmmetteur)
						.Replace("$CodePostalEmmetteur", record.CodePostalEmmetteur)
						.Replace("$RueEmmetteur", record.RueEmmetteur)
						.Replace("$NomEmmetteur", record.NomEmmetteur)
						.Replace("$TelephoneEmmetteur", record.TelephoneEmmetteur)

						.Replace("$date", DateTime.Now.AddDays(1).ToString("dd.MM.yyyy"))
						//.Replace("$Remarque", record.Remarque) // à implémenter
						//.Replace("$pickrem", "") // à implémenter
						.Replace("$NumeroCentreClient", record.NumeroCentreClient.ToString())
						.Replace("$NumeroClient", record.NumeroClient.ToString())
						.Replace("$slaverequest", slaverequest);

					sharedClient.DefaultRequestHeaders.Remove("SOAPAction");
					sharedClient.DefaultRequestHeaders.Add("SOAPAction", "http://www.cargonet.software/CreateMultiShipmentBc");

					StringContent requestContent = new(xmlrequest, Encoding.UTF8, "text/xml");

					// Send the POST request
					using HttpResponseMessage response = await sharedClient.PostAsync("https://e-station-testenv.cargonet.software/eprintwebservice/eprintwebservice.asmx", requestContent);

					// Check the response status and read the content
					if (response.IsSuccessStatusCode)
					{
						string responseContent = await response.Content.ReadAsStringAsync();

						XNamespace ns = "http://www.cargonet.software";
						IEnumerable<XElement> references = XDocument.Parse(responseContent).Descendants(ns + "shipments").Descendants(ns + "BarcodeId");
						var i = 1;
						foreach (var reference in references)
						{
							var shipmentnumber = reference.Value;
							xmlrequest = template_getlabel
							.Replace("$shipmentnumber", shipmentnumber)
							.Replace("$NumeroCentreClient", record.NumeroCentreClient.ToString())
							.Replace("$NumeroClient", record.NumeroClient.ToString());

							sharedClient.DefaultRequestHeaders.Remove("SOAPAction");
							sharedClient.DefaultRequestHeaders.Add("SOAPAction", "http://www.cargonet.software/GetLabelBc");

							requestContent = new StringContent(xmlrequest, Encoding.UTF8, "text/xml");

							// Send the POST request
							using HttpResponseMessage responseLabel = await sharedClient.PostAsync("https://e-station-testenv.cargonet.software/eprintwebservice/eprintwebservice.asmx", requestContent);
							if (responseLabel.IsSuccessStatusCode)
							{
								responseContent = await responseLabel.Content.ReadAsStringAsync();
								XElement image = XDocument.Parse(responseContent).Descendants(ns + "label").First();
								byte[] imageBytes = Convert.FromBase64String(image.Value);
								string file = string.Format("{0}\\{1}-{2}.png", Path.GetDirectoryName(filePath), record.Reference, i);
								File.WriteAllBytes(file, imageBytes);
								//Console.WriteLine(file);
							}
							else
							{
								Console.Error.WriteLine("something went wrong 2");
								Console.WriteLine($"Error: {responseLabel.StatusCode} - {responseLabel.ReasonPhrase}");
								responseContent = await responseLabel.Content.ReadAsStringAsync();
								Console.WriteLine(XDocument.Parse(responseContent).ToString());
							}
							i++;
						}
					}
					else
					{
						Console.Error.WriteLine("something went wrong 3");
						Console.WriteLine($"Error: {response.StatusCode} - {response.ReasonPhrase}");
						string responseContent = await response.Content.ReadAsStringAsync();
						Console.WriteLine(XDocument.Parse(responseContent).ToString());
					}
				}
			}




		}

		public static Task Main(string[] args) => program(args);
	}
}

